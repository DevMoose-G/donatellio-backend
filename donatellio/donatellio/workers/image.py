import os
import uuid
from openai import OpenAI
from donatellio.settings import settings
from PIL import Image
import base64
from io import BytesIO

CURRENT_DIR = os.path.dirname(__file__)

# Configure OpenAI
client = OpenAI(api_key=settings.openai_api_key,)

def generate_image(prompt, n, size, quality) -> str:
    image_name = f"{str(uuid.uuid4())}.png"

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
        img = Image.open(BytesIO(img_bytes))
        img.save(f"{CURRENT_DIR}/../static/{image_name}")
        images.append(img)
    
    return f"http://localhost:8000/static/{image_name}"