from datetime import datetime
from typing import Optional
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from donna_api.auth import get_current_user
from donna_api.types import (
    RequestCalculateMeshGenCost,
    RequestCalculateTextureGenCost,
    RequestCreateMesh,
    RequestCreateTexture,
    ResponseGenerateMeshInfo,
    ResponseGenerateTextureInfo,
    step1x_labels,
)
from donna_common.orm import (
    ImageDAL,
    ProjectDAL,
    UserDAL,
    get_image_dal,
    get_project_dal,
    get_user_dal,
)
from donna_common.orm.base import AssetStage
from donna_common.orm.dal.mesh import MeshDAL, get_mesh_dal
from donna_common.orm.dal.project_branch import ProjectBranchDAL, get_project_branch_dal
from donna_common.orm.dal.project_version import ProjectVersionDAL, get_project_version_dal
from donna_common.orm.dal.project_version_asset import ProjectVersionAssetDAL, get_project_version_asset_dal
from donna_common.orm.dal.texture import TextureDAL, get_texture_dal
from donna_common.orm.models.texture import Texture
from donna_common.orm.models.user import User
from donna_common.providers.storage import StorageProvider
from donna_common.redis.redisstream import RedisStream
from donna_common.redis.types import MeshAction, TexturedMeshAction
from donna_worker.worker.mesh import MESH_DIR

load_dotenv()  # reads .env from cwd

router = APIRouter(prefix="/mesh")

mesh_quality_multiplier = {"low": 1, "medium": 2, "high": 3}

texture_quality_multiplier = {"normal": 2, "precise": 4, "stylized": 4}


def calculate_mesh_gen_cost(n_meshes, quality, labels):
    quality_multiplier = mesh_quality_multiplier[quality]
    cost = (n_meshes * quality_multiplier) + len(labels)
    return cost


def calculate_texture_gen_cost(prompt, texture_quality):
    quality_multiplier = texture_quality_multiplier[texture_quality]
    cost = quality_multiplier
    return cost


@router.post("/{project_id}/preview/mesh_cost", status_code=200)
async def api_calculate_mesh_gen_cost(
    req: RequestCalculateMeshGenCost,
    project_id: str,
    current_user: User = Depends(get_current_user),
) -> ResponseGenerateMeshInfo:
    cost = calculate_mesh_gen_cost(req.n_meshes, req.quality, req.labels)
    return ResponseGenerateMeshInfo(cost=cost, labels=step1x_labels)


@router.post("/{project_id}/preview/texture_cost", status_code=200)
async def api_calculate_texture_gen_cost(
    req: RequestCalculateTextureGenCost,
    project_id: str,
    current_user: User = Depends(get_current_user),
) -> ResponseGenerateTextureInfo:
    cost = calculate_texture_gen_cost(req.prompt, req.texture_quality)
    return ResponseGenerateTextureInfo(cost=cost)


@router.post("/{project_id}/create", status_code=202)
async def create_mesh(
    req: RequestCreateMesh,
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    project_branch_dal: ProjectBranchDAL = Depends(get_project_branch_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    mesh_dal: MeshDAL = Depends(get_mesh_dal),
    current_user: User = Depends(get_current_user),
):
    project = await project_dal.get_project_by_id(project_id)
    if current_user.id != project.user_id:
        return JSONResponse(
            status_code=400,
            content={
                "error_msg": "You don't have permission to create a mesh in this project"
            },
        )

    image = await image_dal.get_image_by_id(req.image_id)
    if not image:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "Image not found"},
        )

    stream = RedisStream("requested-jobs")
    await stream.setup_group(new_only=False)

    mesh_cost = calculate_mesh_gen_cost(req.n_meshes, req.quality, req.labels)
    response = await user_dal.charge_credit(
        current_user, mesh_cost, "user_action:generate_mesh"
    )
    if response.success == False:
        return JSONResponse(
            status_code=400, content={"error_msg": "Not enough credits"}
        )

    mesh_ids = []
    
    main_branch = await project_dal.get_main_branch(project_id=project_id)
    
    params = {
                **req.model_dump(),
                "mesh_ids": mesh_ids,
            }
    
    version = await project_branch_dal.create_version(
        branch_id=main_branch.id,
        author_id=current_user.id,
        version_message=f"{req.n_meshes} mesh{'' if req.n_meshes == 1 else 'es'} created",
    )
    
    for _ in range(req.n_meshes):
        mesh_id = str(uuid4())
        mesh_ids.append(mesh_id)

        mesh = await mesh_dal.create_mesh(
            id=mesh_id,
            project_id=project.id,
            image_id=image.id,
            storage_key=None,
            status="PENDING",
        )
        
        await project_branch_dal.perform_action(
            branch_id=main_branch.id,
            author_id=current_user.id,
            new_asset=mesh,
            action_type="generate_mesh",
            parameters=params,
            version_id=version.id
        )

    await stream.send_msg(
        MeshAction(
            project_id=project_id,
            function_name="generate_mesh",
            params=params,
        )
    )

    return {"image_id": req.image_id, "project_id": project_id}


@router.post("/{project_id}/texture", status_code=202)
async def create_texture(
    req: RequestCreateTexture,
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    texture_dal: TextureDAL = Depends(get_texture_dal),
    project_branch_dal: ProjectBranchDAL = Depends(get_project_branch_dal),
    mesh_dal: MeshDAL = Depends(get_mesh_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    current_user: User = Depends(get_current_user),
):
    project = await project_dal.get_project_by_id(project_id)
    if current_user.id != project.user_id:
        return JSONResponse(
            status_code=400,
            content={
                "error_msg": "You don't have permission to create a texture in this project"
            },
        )

    stream = RedisStream("requested-jobs")
    await stream.setup_group(new_only=False)

    texture_cost = calculate_texture_gen_cost(req.prompt, req.texture_quality)
    response = await user_dal.charge_credit(
        current_user, texture_cost, "user_action:generate_texture"
    )
    if response.success == False:
        return JSONResponse(
            status_code=400, content={"error_msg": "Not enough credits"}
        )

    image = await image_dal.get_image_by_id(req.image_id)
    if not image:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "Image not found"},
        )

    mesh = await mesh_dal.get_mesh_by_id(req.mesh_id)
    if not mesh:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "Mesh not found"},
        )

    texture_id = str(uuid4())
    texture = await texture_dal.create_texture(
        id=texture_id,
        project_id=project.id,
        image_id=image.id,
        mesh_id=mesh.id,
        storage_key=None,
        status="PENDING",
    )
    
    main_branch = await project_dal.get_main_branch(project_id=project_id)
    
    params = {**req.model_dump(), "texture_id": texture_id}
    
    await project_branch_dal.perform_action(
        branch_id=main_branch.id,
        author_id=current_user.id,
        new_asset=texture,
        action_type="generate_texture",
        parameters=params,
        version_message="Texture generated"
    )

    await stream.send_msg(
        TexturedMeshAction(
            project_id=project_id,
            function_name="generate_texture",
            params=params,
        )
    )

    return {"image_id": req.image_id, "project_id": project_id}

class RequestRegenerateMesh(BaseModel):
    project_id: str
    mesh_id: str
    face_count: float = None
    level_of_detail: int = None
    surface_thickness: float = None

@router.post("/{project_id}/regen", status_code=202)
async def regenerate_mesh(
    req: RequestRegenerateMesh,
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    project_branch_dal: ProjectBranchDAL = Depends(get_project_branch_dal),
    project_version_dal: ProjectVersionDAL = Depends(get_project_version_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    mesh_dal: MeshDAL = Depends(get_mesh_dal),
    current_user: User = Depends(get_current_user),
):
    
    project = await project_dal.get_project_by_id(req.project_id)
    if current_user.id != project.user_id:
        return JSONResponse(
            status_code=400,
            content={
                "error_msg": "You don't have permission to create a mesh in this project"
            },
        )

    old_mesh = await mesh_dal.get_mesh_by_id(req.mesh_id)
    if not old_mesh:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "Mesh not found"},
        )
    
    new_mesh_id = str(uuid4())
    # copy old mesh (except octree_res, mc_level, face_count, & storage_key)
    new_mesh = await mesh_dal.create_mesh(
        id=new_mesh_id,
        project_id=project.id,
        image_id=old_mesh.image_id,
        parent_mesh_id=old_mesh.id,
        seed=old_mesh.seed,
        num_inference_steps=old_mesh.num_inference_steps,
        guidance_scale=old_mesh.guidance_scale,
        label=old_mesh.label,
        caption=old_mesh.caption,
        latents_storage_key=old_mesh.latents_storage_key,
        status="PENDING"
    )
    
    stream = RedisStream("requested-jobs")
    await stream.setup_group(new_only=False)
    
    main_branch = await project_dal.get_main_branch(project_id=project_id)
    
    version_msg = "Regenerate mesh and/or Reduce face count of mesh"
    # if req.level_of_detail != None and req.surface_thickness != None:
    #     version_msg += "Regenerate mesh from latents with updated options"
    # elif req.simplify_ratio != None:
    #     version_msg += "Reduce the face count of mesh"
    version = await project_branch_dal.create_version(
        branch_id=main_branch.id,
        author_id=current_user.id,
        version_message=version_msg
    )
    
    actions_performed = []
    if req.level_of_detail != None and req.surface_thickness != None: # temp
        # create a new mesh (copy of the old one?) do it here or in worker (not in both)
        # await mesh_dal.update_mesh(id=req.mesh_id, status="PENDING")
        
        if req.level_of_detail < 1 or req.level_of_detail > 5:
            await project_version_dal.hard_delete_version(version_id=version.id)
            return JSONResponse(
                status_code=400,
                content={"error_msg": "Invalid level of detail"},
            )
        
        octree_resolution = ""
        if req.level_of_detail == 1:
            octree_resolution = 128
        elif req.level_of_detail == 2:
            octree_resolution = 256
        elif req.level_of_detail == 3:
            octree_resolution = 384
        elif req.level_of_detail == 4:
            octree_resolution = 512
        elif req.level_of_detail == 5:
            octree_resolution = 768
        
        # check if mesh needs to be regenerated
        if old_mesh.octree_resolution != str(octree_resolution) or old_mesh.mc_level != req.surface_thickness:
        
            params = {
                "project_id": project.id,
                "mesh_id": new_mesh.id,
                "mc_level": -1 * req.surface_thickness,
                "octree_resolution": octree_resolution,
                "old_mesh_id": old_mesh.id,
            }
            
            await stream.send_msg(
                MeshAction(
                    project_id=req.project_id,
                    function_name="regenerate_from_latents",
                    params=params,
                )
            )
            
            main_branch = await project_dal.get_main_branch(project_id=project_id)
            
            actions_performed.append(await project_branch_dal.perform_action(
                branch_id=main_branch.id,
                author_id=current_user.id,
                new_asset=new_mesh,
                action_type="regenerate_from_latents",
                parameters=params,
                version_id=version.id,
            ))
            
        else:
            print("Mesh does not need to be regenerated")
    if req.face_count != None:
        simplify_ratio = req.face_count / old_mesh.face_count
        if simplify_ratio >= 1 or simplify_ratio <= 0:
            await project_version_dal.hard_delete_version(version_id=version.id)
            return JSONResponse(
                status_code=400,
                content={"error_msg": "Invalid face count"},
            )
        
        params = {"simplify_ratio": simplify_ratio, "new_mesh_id": new_mesh.id, "mesh_id": old_mesh.id}
        await stream.send_msg(
            MeshAction(
                project_id=req.project_id,
                function_name="simplify_mesh",
                params=params,
            )
        )
        
        main_branch = await project_dal.get_main_branch(project_id=project_id)
        
        if len(actions_performed) == 0:
            # mesh is not being regenerated from latents, so copy over old_mesh's stats
            new_mesh = await mesh_dal.update_mesh(
                id=new_mesh.id,
                mc_level=old_mesh.mc_level,
                octree_resolution=old_mesh.octree_resolution,
            )
        
        actions_performed.append(await project_branch_dal.perform_action(
            branch_id=main_branch.id,
            author_id=current_user.id,
            new_asset=new_mesh,
            action_type="simplify_mesh",
            parameters=params,
            version_id=version.id,
        ))
    
    if len(actions_performed) == 0:
        await mesh_dal.delete_mesh(new_mesh)
        await project_version_dal.hard_delete_version(version_id=version.id)
        return JSONResponse(
            status_code=400,
            content={"error_msg": "Mesh does not need to be regenerated or simplified"},
        )

    return {"project_id": req.project_id, "mesh_id": new_mesh.id}

class GetMeshInfo(BaseModel):
    project_id: str
    source_image_url: str
    mesh_quality: str
    created_at: datetime
    level_of_detail: Optional[int] = None
    mc_level: Optional[float] = None
    num_faces: Optional[int] = None

@router.get("/{mesh_id}")
async def get_mesh_info(
    mesh_id: str, 
    mesh_dal: MeshDAL = Depends(get_mesh_dal), 
    project_dal: ProjectDAL = Depends(get_project_dal),
    image_dal: ImageDAL = Depends(get_image_dal), 
    current_user: User = Depends(get_current_user)
):
    
    mesh = await mesh_dal.get_mesh_by_id(mesh_id)
    if not mesh:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "Mesh not found"},
        )
    project = await project_dal.get_project_by_id(mesh.project_id)
    
    if current_user.id != project.user_id:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "You don't have permission to view this mesh"},
        )
    
    storage_provider = StorageProvider()
    image = await image_dal.get_image_by_id(mesh.image_id)
    image_url = storage_provider.generate_get_url(image.storage_key)
    
    mesh_quality = ""
    if mesh.num_inference_steps == 30:
        mesh_quality = "low"
    elif mesh.num_inference_steps == 50:
        mesh_quality = "medium"
    elif mesh.num_inference_steps == 70:
        mesh_quality = "high"
    
    lod = None
    if mesh.octree_resolution == None:
        lod = 0 # TEMP
    elif int(mesh.octree_resolution) == 128:
        lod = 1
    elif int(mesh.octree_resolution) == 256:
        lod = 2
    elif int(mesh.octree_resolution) == 384:
        lod = 3
    elif int(mesh.octree_resolution) == 512:
        lod = 4
    elif int(mesh.octree_resolution) == 768:
        lod = 5
    else:
        raise Exception(f"Invalid octree resolution for mesh {mesh_id}")
    return GetMeshInfo(
        project_id=mesh.project_id,
        num_faces=mesh.face_count,
        source_image_url=image_url,
        mesh_quality=mesh_quality,
        level_of_detail=lod,
        mc_level=0 if mesh.mc_level == None else mesh.mc_level,
        created_at=mesh.created_at
    )

@router.get("/{asset_id}/download")
async def get_mesh_format_download(
    asset_id: str, 
    format: str,
    textured: Optional[bool] = False,
    mesh_dal: MeshDAL = Depends(get_mesh_dal), 
    texture_dal: TextureDAL = Depends(get_texture_dal),
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user)
):
    if textured:
        asset = await texture_dal.get_texture_by_id(asset_id)
    else:
        asset = await mesh_dal.get_mesh_by_id(asset_id)
    project = await project_dal.get_project_by_id(asset.project_id)
    if current_user.id != project.user_id:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "You don't have permission to view this mesh"},
        )
    
    format = format.lower()
    if format not in ['glb', 'fbx', 'obj', 'blend', 'stl']:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "Invalid format"},
        )
    
    storage_provider = StorageProvider()
    mesh_path = f"{MESH_DIR}/{asset_id}.{format}"
    mesh_type = ""
    if format == "glb":
        storage_provider.download_file(asset.storage_key, mesh_path)
        mesh_type = "model/gltf-binary"
        # mesh_url = storage_provider.generate_get_url(mesh.storage_key)
    else:
        storage_provider.download_file(asset.format_storage_keys[format], mesh_path)
        
        if (format == "blend"):
            mesh_type = "application/octet-stream"
        elif (format == "fbx"):
            mesh_type = "application/octet-stream"
        elif (format == "obj"):
            mesh_type = "model/obj"
        elif (format == "stl"):
            mesh_type = "model/stl"
        # mesh_url = storage_provider.generate_get_url(mesh.format_storage_keys[format])
    
    return FileResponse(
        path=mesh_path,
        media_type=mesh_type,
        filename=f"export.{format}"
    )

@router.delete("/{mesh_id}", status_code=200)
async def delete_mesh(
    mesh_id: str,
    mesh_dal: MeshDAL = Depends(get_mesh_dal),
    project_dal: ProjectDAL = Depends(get_project_dal),
    project_version_dal: ProjectVersionDAL = Depends(get_project_version_dal),
    project_version_asset_dal: ProjectVersionAssetDAL = Depends(get_project_version_asset_dal),
    texture_dal: TextureDAL = Depends(get_texture_dal),
    current_user: User = Depends(get_current_user)
):
    mesh = await mesh_dal.get_mesh_by_id(mesh_id)
    if not mesh:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "Mesh not found"},
        )
    project = await project_dal.get_project_by_id(mesh.project_id)
    if current_user.id != project.user_id:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "You don't have permission to delete this mesh"},
        )

    texture_ids = []
    textures = await texture_dal.get_textures_by(Texture.mesh_id == mesh_id)
    texture_ids = [texture.id for texture in textures]

    # delete all version_assets
    versions = await project_version_dal.get_all_versions(project.id)
    for version in versions:
        assets = version.assets
        for asset in assets:
            if asset.asset_id == mesh_id and asset.asset_type == AssetStage.mesh:
                await project_version_asset_dal.unlink_asset(version.id, "mesh", asset.asset_id)
            elif asset.asset_id in texture_ids and asset.asset_type == AssetStage.texture:
                await project_version_asset_dal.unlink_asset(version.id, "texture", asset.asset_id)
    
    # delete all textures
    for texture_id in texture_ids:
        await texture_dal.delete_texture(texture_id)

    await mesh_dal.delete_mesh(mesh)