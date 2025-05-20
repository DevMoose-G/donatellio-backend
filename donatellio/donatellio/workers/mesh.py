import io
import os
from typing import List
import uuid
from openai import OpenAI
import requests
from donatellio.consts import BASE_URL
from donatellio.orm.dal.mesh import MeshDAL
from donatellio.providers.storage import StorageProvider
from donatellio.providers.runpod import RunpodProvider
from donatellio.workers.prompts import ELABORATION_PROMPT, IMAGE_GEN_PROMPT
from donatellio.orm.dal.image import ImageDAL
from donatellio.orm.main import AsyncSessionLocal, get_db
from donatellio.orm.models.image import Image
from donatellio.settings import settings
import PIL.Image
import base64
from io import BytesIO

CURRENT_DIR = os.path.dirname(__file__)

STATIC_DIR = f"{CURRENT_DIR}/../../static"

# Configure OpenAI
client = OpenAI(api_key=settings.openai_api_key,)

async def generate_mesh(image_id, project_id) -> str:

    # generate presigned url
    mesh_id = str(uuid.uuid4())
    storage_provider = StorageProvider()
    presigned_url = storage_provider.generate_put_url_for_mesh(mesh_id)

    # call generate_mesh in runpod
    runpod_service = RunpodProvider()
    await runpod_service.generate_mesh(project_id=project_id, image_id=image_id, mesh_id=mesh_id, presigned_url=presigned_url)
    
    return mesh_id