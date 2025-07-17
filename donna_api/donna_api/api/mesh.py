from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from donna_api.auth import get_current_user
from donna_api.common.models import get_mesh_info
from donna_api.types import (
    RequestCalculateMeshGenCost,
    RequestCalculateTextureGenCost,
    RequestCreateMesh,
    RequestCreateTexture,
    ResponseGenerateMeshInfo,
    ResponseGenerateTextureInfo,
    step1x_labels,
)
from donna_api.utils import (
    calculate_mesh_gen_cost,
    calculate_texture_gen_cost,
    expected_mesh_gen_time,
    expected_texture_gen_time,
    regen_mesh_cost,
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
from donna_common.orm.dal.project_version import (
    ProjectVersionDAL,
    get_project_version_dal,
)
from donna_common.orm.dal.project_version_asset import (
    ProjectVersionAssetDAL,
    get_project_version_asset_dal,
)
from donna_common.orm.dal.texture import TextureDAL, get_texture_dal
from donna_common.orm.models.texture import Texture
from donna_common.orm.models.user import User
from donna_common.providers.storage import StorageProvider
from donna_common.redis.rq import RedisQueue
from donna_worker.worker.mesh import MESH_DIR

load_dotenv()  # reads .env from cwd

router = APIRouter(prefix="/mesh")


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
    cost = calculate_texture_gen_cost(req.texture_quality)
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

    queue = RedisQueue()

    mesh_cost = calculate_mesh_gen_cost(req.n_meshes, req.quality, req.labels)
    response = await user_dal.charge_credit(
        current_user, mesh_cost, "user_action:generate_mesh"
    )
    if response.success == False:
        return JSONResponse(
            status_code=400, content={"error_msg": "Not enough credits"}
        )

    main_branch = await project_dal.get_main_branch(project_id=project_id)

    version = await project_branch_dal.create_version(
        branch_id=main_branch.id,
        author_id=current_user.id,
        version_message=f"{req.n_meshes} mesh{'' if req.n_meshes == 1 else 'es'} created",
    )

    mesh_ids = [str(uuid4()) for _ in range(req.n_meshes)]

    params = {
        **req.model_dump(),
        "mesh_ids": mesh_ids,
    }
    for mesh_id in mesh_ids:
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
            version_id=version.id,
        )

    job_ids = []
    seconds_offset = 0
    for mesh_id in mesh_ids:
        seconds_offset += (
            30 if req.quality == None else expected_mesh_gen_time(req.quality)
        )
        job_id = queue.queue_mesh_action(
            "donna_worker.worker.mesh.generate_mesh",
            expected_at=datetime.now(timezone.utc) + timedelta(seconds=seconds_offset),
            mesh_id=mesh_id,
            project_id=project_id,
            image_id=req.image_id,
            quality=req.quality,
            labels=req.labels,
            seed=req.seed,
            max_polygon_count=req.max_polygon_count,
            mesh_model=req.mesh_model,
            n_meshes=req.n_meshes,
        )
        job_ids.append(job_id)

    return {"image_id": req.image_id, "project_id": project_id, "job_ids": job_ids}


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

    texture_cost = calculate_texture_gen_cost(req.texture_quality)
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
        version_message="Texture generated",
    )

    queue = RedisQueue()
    seconds_offset = expected_texture_gen_time(req.texture_quality)
    queue.queue_texture_action(
        func_callback="donna_worker.worker.mesh.generate_texture",
        expected_at=datetime.now(timezone.utc) + timedelta(seconds=seconds_offset),
        project_id=project_id,
        texture_id=texture_id,
        mesh_id=mesh.id,
        image_id=image.id,
        prompt=req.prompt,
        texture_quality=req.texture_quality,
        seed=req.seed,
    )

    return {"image_id": req.image_id, "project_id": project_id, "job_id": job_id}


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

    if current_user.credit_balance < 1:
        return JSONResponse(
            status_code=400, content={"error_msg": "Not enough credits"}
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
        status="PENDING",
    )

    main_branch = await project_dal.get_main_branch(project_id=project_id)

    version_msg = "Regenerate mesh and/or Reduce face count of mesh"
    version = await project_branch_dal.create_version(
        branch_id=main_branch.id, author_id=current_user.id, version_message=version_msg
    )

    actions_performed = []
    if req.level_of_detail != None and req.surface_thickness != None:  # temp
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
        if (
            old_mesh.octree_resolution != str(octree_resolution)
            or old_mesh.mc_level != -1 * req.surface_thickness
        ):
            params = {
                "project_id": project.id,
                "mesh_id": new_mesh.id,
                "mc_level": -1 * req.surface_thickness,
                "octree_resolution": octree_resolution,
                "old_mesh_id": old_mesh.id,
                "n_faces": None,
            }

            if req.face_count != None and req.face_count != old_mesh.face_count:
                simplify_ratio = req.face_count / old_mesh.face_count

                if simplify_ratio >= 1 or simplify_ratio <= 0:
                    await project_version_dal.hard_delete_version(version_id=version.id)
                    return JSONResponse(
                        status_code=400,
                        content={"error_msg": "Invalid face count"},
                    )

                params["n_faces"] = req.face_count

            queue = RedisQueue()
            queue.queue_mesh_action(
                func_callback="donna_worker.worker.mesh.regenerate_from_latents",
                expected_at=datetime.now(),
                mesh_id=new_mesh.id,
                **params,
            )

            main_branch = await project_dal.get_main_branch(project_id=project_id)

            actions_performed.append(
                await project_branch_dal.perform_action(
                    branch_id=main_branch.id,
                    author_id=current_user.id,
                    new_asset=new_mesh,
                    action_type="regenerate_from_latents",
                    parameters=params,
                    version_id=version.id,
                )
            )

            actions_performed.append(
                await project_branch_dal.perform_action(
                    branch_id=main_branch.id,
                    author_id=current_user.id,
                    new_asset=new_mesh,
                    action_type="simplify_mesh",
                    parameters=params,
                    version_id=version.id,
                )
            )
            req.face_count = None
        else:
            print("Mesh does not need to be regenerated")

    # need to decide if i want to have two separate jobs for this or one after the other
    # if i do 2 sep jobs, need some way to keep delaying the job until the first one is done
    # if i do 1 job after the other, i need to change the mesh regenerate_mesh worker func to take in another param
    #   and need to send both actions to the version
    if req.face_count != None and req.face_count != old_mesh.face_count:
        simplify_ratio = req.face_count / old_mesh.face_count

        if simplify_ratio >= 1 or simplify_ratio <= 0:
            await project_version_dal.hard_delete_version(version_id=version.id)
            return JSONResponse(
                status_code=400,
                content={"error_msg": "Invalid face count"},
            )

        params = {
            "simplify_ratio": simplify_ratio,
            "mesh_id": old_mesh.id,
            "new_mesh_id": new_mesh.id,
            "project_id": project.id,
        }

        queue = RedisQueue()
        queue.queue_mesh_action(
            func_callback="donna_worker.worker.mesh.simplify_mesh",
            expected_at=datetime.now(timezone.utc) + timedelta(seconds=15),
            mesh_id=old_mesh.id,
            new_mesh_id=new_mesh.id,
            simplify_ratio=simplify_ratio,
        )

        main_branch = await project_dal.get_main_branch(project_id=project_id)

        if len(actions_performed) == 0:
            # mesh is not being regenerated from latents, so copy over old_mesh's stats
            new_mesh = await mesh_dal.update_mesh(
                id=new_mesh.id,
                mc_level=old_mesh.mc_level,
                octree_resolution=old_mesh.octree_resolution,
            )

        actions_performed.append(
            await project_branch_dal.perform_action(
                branch_id=main_branch.id,
                author_id=current_user.id,
                new_asset=new_mesh,
                action_type="simplify_mesh",
                parameters=params,
                version_id=version.id,
            )
        )

    if len(actions_performed) == 0:
        await mesh_dal.delete_mesh(new_mesh)
        await project_version_dal.hard_delete_version(version_id=version.id)
        return JSONResponse(
            status_code=400,
            content={"error_msg": "Mesh does not need to be regenerated or simplified"},
        )
    else:
        # TODO: charge credit
        response = await user_dal.charge_credit(
            current_user, regen_mesh_cost, "user_action:regenerate_mesh"
        )
        if response.success == False:
            return JSONResponse(
                status_code=400,
                content={"error_msg": "User does not have enough credit"},
            )

    return {"project_id": req.project_id, "mesh_id": new_mesh.id}


@router.get("/{mesh_id}")
async def api_get_mesh_info(
    mesh_id: str,
    mesh_dal: MeshDAL = Depends(get_mesh_dal),
    project_dal: ProjectDAL = Depends(get_project_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    current_user: User = Depends(get_current_user),
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

    return await get_mesh_info(mesh_id=mesh.id)


@router.get("/{asset_id}/download")
async def get_mesh_format_download(
    asset_id: str,
    format: str,
    textured: Optional[bool] = False,
    mesh_dal: MeshDAL = Depends(get_mesh_dal),
    texture_dal: TextureDAL = Depends(get_texture_dal),
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user),
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
    if format not in ["glb", "fbx", "obj", "blend", "stl"]:
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

        if format == "blend":
            mesh_type = "application/octet-stream"
        elif format == "fbx":
            mesh_type = "application/octet-stream"
        elif format == "obj":
            mesh_type = "model/obj"
        elif format == "stl":
            mesh_type = "model/stl"
        # mesh_url = storage_provider.generate_get_url(mesh.format_storage_keys[format])

    return FileResponse(
        path=mesh_path, media_type=mesh_type, filename=f"export.{format}"
    )


@router.delete("/{mesh_id}", status_code=200)
async def delete_mesh(
    mesh_id: str,
    mesh_dal: MeshDAL = Depends(get_mesh_dal),
    project_dal: ProjectDAL = Depends(get_project_dal),
    project_version_dal: ProjectVersionDAL = Depends(get_project_version_dal),
    project_version_asset_dal: ProjectVersionAssetDAL = Depends(
        get_project_version_asset_dal
    ),
    texture_dal: TextureDAL = Depends(get_texture_dal),
    current_user: User = Depends(get_current_user),
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
                await project_version_asset_dal.unlink_asset(
                    version.id, "mesh", asset.asset_id
                )
            elif (
                asset.asset_id in texture_ids and asset.asset_type == AssetStage.texture
            ):
                await project_version_asset_dal.unlink_asset(
                    version.id, "texture", asset.asset_id
                )

    # delete all textures
    for texture_id in texture_ids:
        await texture_dal.delete_texture(texture_id)

    await mesh_dal.delete_mesh(mesh)
