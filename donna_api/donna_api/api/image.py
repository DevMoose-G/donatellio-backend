import uuid

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from donna_api.auth import get_current_user
from donna_api.types import (
    RequestCheckElaboratingQuestions,
    RequestCreateImage,
    RequestEditImage,
    RequestGetElaboratingQuestions,
)
from donna_common.orm import (
    ImageDAL,
    ProjectDAL,
    UserDAL,
    get_image_dal,
    get_project_dal,
    get_user_dal,
)
from donna_common.orm.models.user import User
from donna_common.providers.openai import OpenAIProvider
from donna_common.providers.storage import StorageProvider, extract_s3_key
from donna_common.redis.redisstream import RedisStream
from donna_common.redis.types import ImageAction

load_dotenv()  # reads .env from cwd

router = APIRouter(prefix="/image")


class ResponseImage(BaseModel):
    image_id: str
    project_id: str

@router.post("/create", status_code=202)
async def create_image(
    req: RequestCreateImage,
    project_dal: ProjectDAL = Depends(get_project_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    current_user: User = Depends(get_current_user),
):
    project_id = str(uuid.uuid4())
    image_id = str(uuid.uuid4())

    stream = RedisStream("requested-jobs")
    await stream.setup_group(new_only=False)

    response = await user_dal.charge_credit(
        current_user, 2, "user_action:generate_image"
    )
    if response.success == False:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "Not enough credits"},
        )

    await project_dal.create_project(
        id=project_id, name="test", user_id=current_user.id
    )

    await image_dal.create_image(id=image_id, prompt=req.prompt, project_id=project_id)

    await stream.send_msg(
        ImageAction(
            project_id=project_id,
            function_name="generate_image",
            params={**req.model_dump(), "project_id": project_id, "image_id": image_id},
        )
    )

    return ResponseImage(image_id=image_id, project_id=project_id)

@router.post("/{project_id}/edit", status_code=202)
async def edit_image(
    req: RequestEditImage,
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    current_user: User = Depends(get_current_user),
):
    project = await project_dal.get_project_by_id(req.project_id)
    if project.user_id != current_user.id:
        return JSONResponse(
            status_code=403,
            content={"error_msg": "You don't have permission to edit this project"},
        )
    
    stream = RedisStream("requested-jobs")
    image_id = str(uuid.uuid4())
    await stream.setup_group(new_only=False)

    response = await user_dal.charge_credit(current_user, 2, "user_action:edit_image")
    if response.success == False:
        return JSONResponse(
            status_code=400, content={"error_msg": "Not enough credits"}
        )

    if project is None:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "Project doesn't exist"},
        )

    await stream.send_msg(
        ImageAction(
            project_id=project_id,
            function_name="edit_image",
            params={**req.model_dump(), "project_id": project_id, "image_id": image_id},
        )
    )

    await image_dal.create_image(
        id=image_id,
        prompt=req.prompt,
        project_id=project_id,
        original_image_id=req.original_image_id,
    )

    return ResponseImage(image_id=image_id, project_id=project_id)

class RequestImageCost(BaseModel):
    image_model: str
    quality: str
    
@router.post("/cost", status_code=200)
async def get_image_cost(
    req: RequestImageCost,
    current_user: User = Depends(get_current_user),
):
    if req.image_model == "gpt4o":
        if req.quality == "high":
            cost = 3
        elif req.quality == "medium":
            cost = 2
        elif req.quality == "low":
            cost = 1
    elif req.image_model == "fluxkontext":
        if req.quality == "high":
            cost = 2
        elif req.quality == "medium":
            cost = 1
        elif req.quality == "low":
            cost = 1
    elif req.image_model == "imagen4":
        cost = 1
    return {"cost": cost}

@router.get("/{project_id}/chats", status_code=200)
async def get_image_chat_history(
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user),
):
    
    project = await project_dal.get_project_by_id(project_id)
    
    if project is None:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error_msg": "Project doesn't exist"},
        )
    
    if project.user_id != current_user.id:
        return JSONResponse(
            status_code=403,
            content={"success": False, "error_msg": "You don't have permission to view this project"},
        )
        
    response = await project_dal.get_image_prompt_chats(project_id)
    return response


class RequestGeneratePresignedUrl(BaseModel):
    content_type: str = "image/png"


@router.post("/presign", status_code=202)
async def generate_presigned_url_for_image(
    req: RequestGeneratePresignedUrl,
    project_dal: ProjectDAL = Depends(get_project_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    current_user: User = Depends(get_current_user),
):
    storage_provider = StorageProvider()
    image_id = str(uuid.uuid4())
    presigned_url = storage_provider.generate_put_url_for_image(
        image_id, req.content_type
    )
    return JSONResponse(
        status_code=202, content={"presigned_url": presigned_url, "image_id": image_id}
    )


class RequestUploadImage(BaseModel):
    image_id: str
    presigned_url: str


@router.post("/upload", status_code=202)
async def upload_image(
    request: RequestUploadImage,
    project_dal: ProjectDAL = Depends(get_project_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    current_user: User = Depends(get_current_user),
) -> ResponseImage:
    project_id = str(uuid.uuid4())
    project = await project_dal.create_project(
        id=project_id, name="", user_id=current_user.id
    )
    storage_key = extract_s3_key(request.presigned_url)

    image = await image_dal.create_image(
        id=request.image_id, prompt="Image uploaded", project_id=project.id, storage_key=storage_key
    )

    # name project
    openai_provider = OpenAIProvider()
    await openai_provider.name_project(project_id)

    return ResponseImage(image_id=image.id, project_id=project.id)


@router.post("/elaborate", status_code=200)
async def gen_elaborating_questions(
    req: RequestGetElaboratingQuestions,
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user),
):
    # stream = RedisStream("requested-jobs")
    # await stream.setup_group(new_only=False)

    # project = await project_dal.get_project_by_id(req.project_id)
    # if project is None:
    #     raise HTTPException(400, detail="Invalid Project")

    # TODO: cache this in redis to reduce openai calls
    openai_provider = OpenAIProvider()
    questions = openai_provider.get_elaborating_questions(
        project_id=req.project_id, current_prompt=req.prompt, image_id=req.image_id
    )

    return {"questions": questions}

    # await stream.send_msg(RedisPayload(req.project_id, "edit_image", req.model_dump()))

    # return {"project_id": req.project_id}


@router.post("/check_elaborate", status_code=200)
async def post_check_elaborating_questions(
    req: RequestCheckElaboratingQuestions,
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user),
):
    openai_provider = OpenAIProvider()
    questions = openai_provider.check_elaborating_questions(
        current_prompt=req.prompt, elaborating_questions=req.elaborating_questions
    )

    # free users only get the initial 3 questions
    if (
        len(questions) <= 1
        and len(req.prompt) < 512
        and current_user.subscription_tier != "free"
    ):
        questions = openai_provider.get_elaborating_questions(None, req.prompt, None)
    return {"questions": questions}
