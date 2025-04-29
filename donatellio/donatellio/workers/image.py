import os
import uuid
from openai import OpenAI
import requests
from donatellio.consts import BASE_URL
from donatellio.orm.dal.image import ImageDAL
from donatellio.orm.main import get_db
from donatellio.orm.models.image import Image
from donatellio.settings import settings
import PIL
import base64
from io import BytesIO

CURRENT_DIR = os.path.dirname(__file__)

# Configure OpenAI
client = OpenAI(api_key=settings.openai_api_key,)

def generate_image(prompt, n, size, quality) -> str:
    if n!=1:
        n=1
    
    img_id = str(uuid.uuid4())
    image_name = f"{img_id}.png"

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
        img.save(f"{CURRENT_DIR}/../static/{image_name}")
        images.append(img)
    
    img_url = f"http://localhost:8000/static/{image_name}"

    ImageDAL(get_db()).create_image(Image(id, prompt, ))

    return img_url

def edit_image(original_image_url, prompt, n, size, quality) -> str:
    if n!=1:
        n=1
    image_name = f"{str(uuid.uuid4())}.png"

    response = requests.get(original_image_url)
    img = PIL.Image.open(BytesIO(response.content))

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
        img.save(f"{CURRENT_DIR}/../static/{image_name}")
        images.append(img)
    
    return f"{BASE_URL}/static/{image_name}"