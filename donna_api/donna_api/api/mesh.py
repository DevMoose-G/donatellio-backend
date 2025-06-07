from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from donna_api.auth import get_current_user
from donna_api.types import (
    BaseResponse,
    RequestCalculateMeshGenCost,
    RequestCalculateTextureGenCost,
    RequestCreateMesh,
    RequestCreateTexture,
    ResponseCalculateMeshGenCost,
)
from donna_common.orm import (
    ImageDAL,
    ProjectDAL,
    UserDAL,
    get_image_dal,
    get_project_dal,
    get_user_dal,
)
from donna_common.orm.dal.mesh import MeshDAL, get_mesh_dal
from donna_common.orm.models.user import User
from donna_common.redis.redisstream import RedisStream
from donna_common.redis.types import MeshAction

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


@router.post("/{project_id}/mesh_cost", status_code=200)
async def api_calculate_mesh_gen_cost(
    req: RequestCalculateMeshGenCost,
    project_id: str,
    current_user: User = Depends(get_current_user),
) -> ResponseCalculateMeshGenCost:
    cost = calculate_mesh_gen_cost(req.n_meshes, req.quality, req.labels)
    return JSONResponse(status_code=200, content={"cost": cost})


@router.post("/{project_id}/texture_cost", status_code=200)
async def api_calculate_mesh_gen_cost(
    req: RequestCalculateTextureGenCost,
    project_id: str,
    current_user: User = Depends(get_current_user),
) -> ResponseCalculateMeshGenCost:
    cost = calculate_texture_gen_cost(req.prompt, req.texture_quality)
    return JSONResponse(status_code=200, content={"cost": cost})


@router.post("/{project_id}/create", status_code=202)
async def create_mesh(
    req: RequestCreateMesh,
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    mesh_dal: MeshDAL = Depends(get_mesh_dal),
    current_user: User = Depends(get_current_user),
):
    # TODO: should i have a check here if the user is the owner of the project
    stream = RedisStream("requested-jobs")
    await stream.setup_group(new_only=False)

    mesh_cost = calculate_mesh_gen_cost(req.n_meshes, req.quality, req.labels)
    response = await user_dal.charge_credit(
        current_user, mesh_cost, "user_action:generate_mesh"
    )
    if response.success == False:
        return BaseResponse(success=False, message="Not enough credits")

    msg_id = await stream.send_msg(
        # RedisPayload(project_id, "generate_mesh", {**req.model_dump()})
        MeshAction(
            project_id=project_id,
            function_name="generate_mesh",
            params={**req.model_dump()},
        )
    )

    return {"image_id": req.image_id, "project_id": project_id}


@router.post("/{project_id}/texture", status_code=202)
async def create_texture(
    req: RequestCreateTexture,
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    mesh_dal: MeshDAL = Depends(get_mesh_dal),
    current_user: User = Depends(get_current_user),
):
    stream = RedisStream("requested-jobs")
    await stream.setup_group(new_only=False)

    texture_cost = calculate_texture_gen_cost(req.prompt, req.texture_quality)
    response = await user_dal.charge_credit(
        current_user, texture_cost, "user_action:generate_texture"
    )
    if response.success == False:
        return BaseResponse(success=False, message="Not enough credits")

    msg_id = await stream.send_msg(
        MeshAction(
            project_id=project_id,
            function_name="generate_texture",
            params={**req.model_dump()},
        )
    )

    return {"image_id": req.image_id, "project_id": project_id}
