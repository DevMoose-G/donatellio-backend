import os
from typing import List
import uuid
from openai import OpenAI
import requests
from donatellio.consts import BASE_URL
from donatellio.workers.prompts import ELABORATION_PROMPT
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

async def generate_image(project_id, prompt, n, size, quality) -> str:
    if n!=1:
        n=1
    
    img_id = str(uuid.uuid4())
    image_name = f"{img_id}.png"

    prompt += "\nDon't put any background. Image has to be transparent."

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
        await ImageDAL(session).create_image(Image(id=img_id, prompt=prompt, project_id=project_id, url=img_url, original_image_url=None))

    return img_url

async def edit_image(project_id, original_image_url, prompt, n, size, quality) -> str:
    img_id = str(uuid.uuid4())
    image_name = f"{img_id}.png"

    response = requests.get(original_image_url)
    img = PIL.Image.open(BytesIO(response.content))

    prompt += "\nImage has to have a transparent background."

    res = client.images.edit(
        model="gpt-image-1",
        image=[
            img
        ],
        prompt=prompt,
        n=n,
        size=size,
        quality=quality,
        background="transparent" # not sure if this param is allowed
    )

    images = []
    for img_data in res.data:
        img_bytes = base64.b64decode(img_data.b64_json)
        img = PIL.Image.open(BytesIO(img_bytes))
        img.save(f"{STATIC_DIR}/{image_name}")
        images.append(img)
    
    img_url = f"{BASE_URL}/static/{image_name}"

    async with AsyncSessionLocal() as session:
        await ImageDAL(session).create_image(Image(img_id, prompt, project_id, img_url, original_image_url))
    
    return img_url

def get_elaborating_questions(project_id: str, current_prompt: str, image_id: str=None) -> List[str]:
    res = client.completions.create(model="gpt-4.1-mini", prompt=f"{ELABORATION_PROMPT}\n\n{current_prompt}", max_tokens=128)
    questions_str = res.choices[0].text
    questions = questions_str.split("\n")
    assert len(questions) > 1
    return questions