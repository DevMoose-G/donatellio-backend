import os
import subprocess
from pathlib import Path
from typing import Dict, List

import PIL.Image
from openai import OpenAI

from donna_common.orm.dal.mesh import MeshDAL
from donna_common.orm.dal.project import ProjectDAL
from donna_common.orm.dal.project_branch import ProjectBranchDAL
from donna_common.orm.dal.texture import TextureDAL
from donna_common.orm.main import AsyncSessionLocal
from donna_common.orm.models.mesh import Mesh
from donna_common.orm.models.texture import Texture
from donna_common.providers.runpod import RunpodProvider
from donna_common.providers.storage import StorageProvider
from donna_common.settings import settings

async def initialize_branches() -> None:
    async with AsyncSessionLocal() as session:
        projects = await ProjectDAL(session).get_all_projects()

        for project in projects:
            if project.branches == []:
                await ProjectBranchDAL(session).create_branch(project_id=project.id, author_id=project.user_id, name="main")