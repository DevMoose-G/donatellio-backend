import io
import os
from typing import List
import uuid
from openai import OpenAI
import requests
from donatellio.consts import BASE_URL
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

async def generate_mesh(image_id, project_id, prompt, size, quality) -> str:
    async with AsyncSessionLocal() as session:
        image = await ImageDAL(session).get_image_by_id(image_id)
    image_name = f"{image_id}.png"

    prompt += f"\n{IMAGE_GEN_PROMPT}"

    res = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        n=n,
        size=size,
        quality=quality,
        background="transparent"
    )

    images = []
    for img_data in res.data:
        img_bytes = base64.b64decode(img_data.b64_json)
        img = PIL.Image.open(BytesIO(img_bytes))
        img.save(f"{STATIC_DIR}/{image_name}")
        images.append(img)
    
    img_url = f"{BASE_URL}/static/{image_name}"
    
    async with AsyncSessionLocal() as session:
        await ImageDAL(session).update_image(id=image_id, project_id=project_id, url=img_url)

    return img_url