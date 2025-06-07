from typing import List

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from donna_api.auth import get_current_user
from donna_api.types import BaseResponse
from donna_common.orm import ProjectDAL, get_project_dal
from donna_common.orm.models.user import User

load_dotenv()  # reads .env from cwd

router = APIRouter(prefix="/project")


@router.delete("/{project_id}", status_code=200)
async def delete_project(
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user),
):
    project = await project_dal.get_project_by_id(project_id)
    if current_user.id != project.user_id:
        return BaseResponse(
            success=False, message="You don't have permission to delete this project"
        )
    await project_dal.hard_delete_project(project.id)
    return {"success": True}


class MoveProjectRequest(BaseModel):
    collections_to_add: List[str]
    collections_to_remove: List[str]


@router.post("/{project_id}/move", status_code=200)
async def move_project(
    project_id: str,
    req: MoveProjectRequest,
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user),
):
    await project_dal.get_project_by_id(project_id)
