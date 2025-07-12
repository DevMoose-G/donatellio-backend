from donna_common.orm.dal.project import ProjectDAL
from donna_common.orm.dal.project_branch import ProjectBranchDAL
from donna_common.orm.main import AsyncSessionLocal


async def initialize_branches() -> None:
    async with AsyncSessionLocal() as session:
        projects = await ProjectDAL(session).get_all_projects()

        for project in projects:
            if project.branches == []:
                await ProjectBranchDAL(session).create_branch(
                    project_id=project.id, author_id=project.user_id, name="main"
                )
