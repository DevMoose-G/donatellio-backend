import io
import os
from typing import List
import uuid
from openai import OpenAI
import requests
from donatellio.consts import BASE_URL
from donatellio.redisstream import RedisPayload, RedisStream
from donatellio.providers.runpod import RunpodProvider
from donatellio.providers.storage import StorageProvider
from donatellio.workers.prompts import CHECK_ELABORATION_PROMPT, ELABORATION_PROMPT, IMAGE_GEN_PROMPT
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

async def generate_image(image_id, project_id, prompt, n, size, quality) -> str:
    if n!=1:
        n=1
    
    image_name = f"{image_id}.png"

    prompt = f"{IMAGE_GEN_PROMPT}\n{prompt}"
    
    # wake up geometry pipeline
    runpod_service = RunpodProvider()
    await runpod_service.wake_up_geometry()

    stream = client.responses.create(
        model="gpt-4.1",
        input=prompt,
        tools=[{
            "type": "image_generation",
            "background": "transparent",
            "quality": quality,
            "size": size,
            "partial_images": 2
        }],
        stream=True
    )
    
    async with AsyncSessionLocal() as session:
        image = await ImageDAL(session).get_image_by_id(image_id)
    
    completed_images_stream = RedisStream("completed-jobs", group_name="image")
    
    for event in stream:
        if event.type == "response.image_generation_call.partial_image":
            idx = event.partial_image_index
            image_base64 = event.partial_image_b64
            image_bytes = base64.b64decode(image_base64)
            
            img_filepath = f"{STATIC_DIR}/{image_id}_partial{idx}.png"
            with open(img_filepath, "wb") as f:
                f.write(image_bytes)
            
            storage_provider = StorageProvider()
            key = storage_provider.upload_image(image_name, img_filepath)
            
            if image.storage_key == None:
                async with AsyncSessionLocal() as session:
                    await ImageDAL(session).update_image(id=image_id, project_id=project_id, storage_key=key)
            await completed_images_stream.send_msg(RedisPayload(project_id, "generate_image", {"image_id": image_id}))
        if event.type == "response.image_generation_call.completed":
            async with AsyncSessionLocal() as session:
                await ImageDAL(session).update_image(id=image_id, external_id=event.item_id)

    return key

async def edit_image(image_id, project_id, original_image_id, prompt, n, size, quality) -> str:
    image_name = f"{image_id}.png"
    
    async with AsyncSessionLocal() as session:
        original_image = await ImageDAL(session).get_image_by_id(original_image_id)
        assert original_image is not None

    # TODO: get directly with aws sdk python
    storage_provider = StorageProvider()
    og_image_url = storage_provider.generate_get_url(original_image.storage_key)
    response = requests.get(og_image_url)
    img = PIL.Image.open(BytesIO(response.content))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    runpod_service = RunpodProvider()
    await runpod_service.wake_up_geometry()

    prompt = f"{IMAGE_GEN_PROMPT}\n{prompt}"

    stream = client.responses.create(
        model="gpt-4.1",
        input=[
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}]
            },
            {
                "type": "image_generation_call",
                "id": original_image.external_id
            }
        ],
        tools=[{
            "type": "image_generation",
            "background": "transparent",
            "quality": quality,
            "size": size,
            "partial_images": 2
        }],
        stream=True
    )

    async with AsyncSessionLocal() as session:
        image = await ImageDAL(session).get_image_by_id(image_id)
    
    completed_images_stream = RedisStream("completed-jobs", group_name="image")
    
    for event in stream:
        if event.type == "response.image_generation_call.partial_image":
            idx = event.partial_image_index
            image_base64 = event.partial_image_b64
            image_bytes = base64.b64decode(image_base64)
            
            img_filepath = f"{STATIC_DIR}/{image_id}_partial{idx}.png"
            with open(img_filepath, "wb") as f:
                f.write(image_bytes)
            
            storage_provider = StorageProvider()
            key = storage_provider.upload_image(image_name, img_filepath)
            
            if image.storage_key == None:
                async with AsyncSessionLocal() as session:
                    await ImageDAL(session).update_image(id=image_id, project_id=project_id, storage_key=key)
            await completed_images_stream.send_msg(RedisPayload(project_id, "edit_image", {"image_id": image_id}))
        if event.type == "response.image_generation_call.completed":
            async with AsyncSessionLocal() as session:
                await ImageDAL(session).update_image(id=image_id, external_id=event.item_id)
    
    return key

def get_elaborating_questions(project_id: str, current_prompt: str, image_id: str=None) -> List[str]:
    res = client.responses.create(model="gpt-4.1-mini", instructions=ELABORATION_PROMPT, input=f"{current_prompt}", max_output_tokens=128)
    questions_str = res.output_text
    questions = questions_str.split("\n")
    assert len(questions) > 1
    return questions

def check_elaborating_questions(current_prompt: str, elaborating_questions: List[str]) -> List[str]:
    res = client.responses.create(model="gpt-4.1-mini", instructions=f"{CHECK_ELABORATION_PROMPT}\n{elaborating_questions}", input=f"{current_prompt}", max_output_tokens=128)
    questions_str = res.output_text
    questions = questions_str.split("\n")
    
    return questions