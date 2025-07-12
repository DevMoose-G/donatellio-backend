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
from donna_api.utils import image_cost
from donna_common.orm import (
    ImageDAL,
    ProjectDAL,
    UserDAL,
    get_image_dal,
    get_project_dal,
    get_user_dal,
)
from donna_common.orm.dal.project_branch import ProjectBranchDAL, get_project_branch_dal
from donna_common.orm.dal.styleboard import StyleBoardDAL, get_styleboard_dal
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
    project_branch_dal: ProjectBranchDAL = Depends(get_project_branch_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    styleboard_dal: StyleBoardDAL = Depends(get_styleboard_dal),
    current_user: User = Depends(get_current_user),
):
    project_id = str(uuid.uuid4())
    image_id = str(uuid.uuid4())

    stream = RedisStream("requested-jobs")
    await stream.setup_group(new_only=False)

    cost = image_cost(req.image_model, req.quality, req.style_image_storage_url)
    response = await user_dal.charge_credit(
        current_user, cost, "user_action:generate_image"
    )
    if response.success == False:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "Not enough credits"},
        )

    # create a new StyleBoard if style_image_storage_url is provided
    styleboard_id = None
    if req.style_image_storage_url:
        styleboard = await styleboard_dal.create_styleboard(
            id=project_id,
            name="Unnamed StyleBoard",
            user_id=current_user.id,
            public=False,
        )

        await styleboard_dal.add_image(
            styleboard_id=styleboard.id,
            image_storage_key=extract_s3_key(req.style_image_storage_url),
        )
        styleboard_id = styleboard.id

    # then create a new project with that board linked to it
    user_on_free_tier = current_user.subscription_id == ""
    project = await project_dal.create_project(
        id=project_id,
        name="Unnamed Project",
        user_id=current_user.id,
        public=user_on_free_tier,
        styleboard_id=styleboard_id,
    )

    try:
        main_branch = await project_dal.get_main_branch(project_id=project_id)

        image = await image_dal.create_image(
            id=image_id, prompt=req.prompt, project_id=project_id
        )

        await project_branch_dal.perform_action(
            branch_id=main_branch.id,
            author_id=current_user.id,
            new_asset=image,
            action_type="generate_image",
            parameters={
                **req.model_dump(),
                "project_id": project_id,
                "image_id": image_id,
            },
            version_message="Image created",
        )

        req_params = req.model_dump()
        req_params.pop("style_image_storage_url")
        await stream.send_msg(
            ImageAction(
                type="image",
                image_id=image_id,
                project_id=project_id,
                function_name="generate_image",
                params={**req_params, "project_id": project_id, "image_id": image_id},
            )
        )
    except:
        # delete project
        await project_dal.hard_delete_project(project.id)
        raise

    return ResponseImage(image_id=image_id, project_id=project_id)


@router.post("/{project_id}/edit", status_code=202)
async def edit_image(
    req: RequestEditImage,
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    project_branch_dal: ProjectBranchDAL = Depends(get_project_branch_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    current_user: User = Depends(get_current_user),
):
    project = await project_dal.get_project_by_id(req.project_id)

    if project is None:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "Project doesn't exist"},
        )

    if project.user_id != current_user.id:
        return JSONResponse(
            status_code=403,
            content={"error_msg": "You don't have permission to edit this project"},
        )

    stream = RedisStream("requested-jobs")
    image_id = str(uuid.uuid4())
    await stream.setup_group(new_only=False)

    cost = image_cost(req.image_model, req.quality)
    response = await user_dal.charge_credit(
        current_user, cost, "user_action:edit_image"
    )
    if response.success == False:
        return JSONResponse(
            status_code=400, content={"error_msg": "Not enough credits"}
        )

    await stream.send_msg(
        ImageAction(
            type="image",
            project_id=project_id,
            image_id=image_id,
            function_name="edit_image",
            params={**req.model_dump(), "project_id": project_id, "image_id": image_id},
        )
    )

    image = await image_dal.create_image(
        id=image_id,
        prompt=req.prompt,
        project_id=project_id,
        parent_image_id=req.parent_image_id,
    )

    main_branch = await project_dal.get_main_branch(project_id=project_id)
    await project_branch_dal.perform_action(
        branch_id=main_branch.id,
        author_id=current_user.id,
        new_asset=image,
        action_type="edit_image",
        parameters={**req.model_dump(), "project_id": project_id, "image_id": image_id},
        version_message="Image edited",
    )

    return ResponseImage(image_id=image_id, project_id=project_id)


class RequestImageCost(BaseModel):
    image_model: str
    quality: str
    has_style_image: bool


@router.post("/cost", status_code=200)
async def get_image_cost(
    req: RequestImageCost,
    current_user: User = Depends(get_current_user),
):
    cost = image_cost(req.image_model, req.quality, req.has_style_image)
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
            content={
                "success": False,
                "error_msg": "You don't have permission to view this project",
            },
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
    project_branch_dal: ProjectBranchDAL = Depends(get_project_branch_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    current_user: User = Depends(get_current_user),
) -> ResponseImage:
    project_id = str(uuid.uuid4())
    project = await project_dal.create_project(
        id=project_id,
        name="",
        user_id=current_user.id,
        public=True,  # temp public
    )

    main_branch = await project_dal.get_main_branch(project_id=project_id)

    storage_key = extract_s3_key(request.presigned_url)

    image = await image_dal.create_image(
        id=request.image_id,
        prompt="Image uploaded",
        project_id=project.id,
        storage_key=storage_key,
    )

    # TODO: generate the thumbnail image

    await project_branch_dal.perform_action(
        branch_id=main_branch.id,
        author_id=current_user.id,
        new_asset=image,
        action_type="upload_image",
        parameters={
            "storage_key": storage_key,
            "image_id": image.id,
            "project_id": project.id,
        },
        version_message="Image uploaded",
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
        len(questions) <= 1 and len(req.prompt) < 512
        # and current_user.subscription_tier != "free"
    ):
        questions = openai_provider.get_elaborating_questions(None, req.prompt, None, 2)
    return {"questions": questions}
