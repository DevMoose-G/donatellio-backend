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

async def generate_mesh(image_id, project_id, mesh_model: str, n_meshes: int, quality: str, seed: int, labels: List[str], max_polygon_count: int) -> List[str]:

    # call generate_mesh in runpod
    runpod_service = RunpodProvider()
    return await runpod_service.generate_untextured_mesh(project_id, image_id, mesh_model, n_meshes, quality, seed, labels, max_polygon_count)
    
async def generate_texture(image_id, project_id, mesh_id: str, prompt: str, texture_quality: str, seed: int):
    runpod_service = RunpodProvider()
    return await runpod_service.generate_texture_on_mesh(image_id=image_id, project_id=project_id, mesh_id=mesh_id, prompt=prompt, texture_quality=texture_quality, seed=seed)