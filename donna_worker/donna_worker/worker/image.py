import base64
import io
import os
from io import BytesIO
from typing import List

import openai
import PIL.Image
import requests
from openai import OpenAI

from donna_common.orm.dal.image import ImageDAL
from donna_common.orm.dal.project import ProjectDAL
from donna_common.orm.main import AsyncSessionLocal
from donna_common.providers.runpod import RunpodProvider
from donna_common.providers.storage import StorageProvider
from donna_common.redis.redisstream import RedisStream
from donna_common.redis.types import ImageAction
from donna_common.settings import settings
from donna_worker.worker.prompts import (
    CHECK_ELABORATION_PROMPT,
    ELABORATION_PROMPT,
    IMAGE_GEN_PROMPT,
    NAME_PROJECT_BASED_ON_PROMPT,
)

CURRENT_DIR = os.path.dirname(__file__)

STATIC_DIR = settings.static_dir

# Configure OpenAI
client = OpenAI(
    api_key=settings.openai_api_key,
)


async def name_project(project_id):
    async with AsyncSessionLocal() as session:
        project = await ProjectDAL(session).get_project_by_id(project_id)
        prompt = project.images[0].prompt
    res = client.responses.create(
        model="gpt-4.1-mini",
        instructions=NAME_PROJECT_BASED_ON_PROMPT,
        input=f"{prompt}",
        max_output_tokens=128,
    )
    project_name = res.output_text
    async with AsyncSessionLocal() as session:
        await ProjectDAL(session).update_project(id=project_id, name=project_name)

    return project_name


async def generate_image(image_id, project_id, prompt, n, size, quality) -> str:
    if n != 1:
        n = 1

    image_name = f"{image_id}.png"

    project_name = name_project(project_id)

    prompt = f"{IMAGE_GEN_PROMPT}\n{prompt}"

    # wake up geometry pipeline
    # TEMP
    runpod_service = RunpodProvider()
    await runpod_service.wake_up_geometry()

    stream = client.responses.create(
        model="gpt-4.1",
        input=prompt,
        tools=[
            {
                "type": "image_generation",
                "background": "transparent",
                "quality": quality,
                "size": size,
                "partial_images": 2,
            }
        ],
        stream=True,
    )

    async with AsyncSessionLocal() as session:
        image = await ImageDAL(session).get_image_by_id(image_id)

    completed_images_stream = RedisStream("completed-jobs", group_name="image")

    try:
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
                        await ImageDAL(session).update_image(
                            id=image_id, project_id=project_id, storage_key=key
                        )
                await completed_images_stream.send_msg(
                    ImageAction(
                        project_id=project_id,
                        function_name="generate_image",
                        image_id=image_id,
                        is_partial=True,
                        params={
                            "image_id": image_id,
                            "project_id": project_id,
                            "prompt": prompt,
                            "n": n,
                            "size": size,
                            "quality": quality,
                        },
                    )
                )
            if event.type == "response.image_generation_call.completed":
                async with AsyncSessionLocal() as session:
                    await ImageDAL(session).update_image(
                        id=image_id, external_id=event.item_id
                    )
                await completed_images_stream.send_msg(
                    ImageAction(
                        project_id=project_id,
                        function_name="generate_image",
                        image_id=image_id,
                        is_partial=False,
                        params={
                            "image_id": image_id,
                            "project_id": project_id,
                            "prompt": prompt,
                            "n": n,
                            "size": size,
                            "quality": quality,
                        },
                    )
                )
    except openai.APIError as e:
        print(e)
        await completed_images_stream.send_msg(
            ImageAction(
                project_id=project_id,
                function_name="generate_image",
                image_id=image_id,
                is_partial=False,
                params={
                    "image_id": image_id,
                    "project_id": project_id,
                    "prompt": prompt,
                    "n": n,
                    "size": size,
                    "quality": quality,
                },
                successful=False,
            )
        )

    await project_name
    return key


async def edit_image(
    image_id, project_id, original_image_id, prompt, n, size, quality
) -> str:
    if prompt == "":
        raise Exception("Prompt cannot be empty")

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
            {"role": "user", "content": [{"type": "input_text", "text": prompt}]},
            {"type": "image_generation_call", "id": original_image.external_id},
        ],
        tools=[
            {
                "type": "image_generation",
                "background": "transparent",
                "quality": quality,
                "size": size,
                "partial_images": 2,
            }
        ],
        stream=True,
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
                    await ImageDAL(session).update_image(
                        id=image_id, project_id=project_id, storage_key=key
                    )
            await completed_images_stream.send_msg(
                # ImagePayload(
                #     project_id, "edit_image", image_id=image_id, is_partial=True
                # )
                ImageAction(
                    project_id=project_id,
                    function_name="edit_image",
                    image_id=image_id,
                    is_partial=True,
                    params={
                        "image_id": image_id,
                        "project_id": project_id,
                        "original_image_id": original_image_id,
                        "prompt": prompt,
                        "n": n,
                        "size": size,
                        "quality": quality,
                    },
                )
            )
        if event.type == "response.image_generation_call.completed":
            async with AsyncSessionLocal() as session:
                await ImageDAL(session).update_image(
                    id=image_id, external_id=event.item_id
                )
            await completed_images_stream.send_msg(
                # ImagePayload(
                #     project_id, "edit_image", image_id=image_id, is_partial=False
                # )
                ImageAction(
                    project_id=project_id,
                    function_name="edit_image",
                    image_id=image_id,
                    is_partial=False,
                    params={
                        "image_id": image_id,
                        "project_id": project_id,
                        "original_image_id": original_image_id,
                        "prompt": prompt,
                        "n": n,
                        "size": size,
                        "quality": quality,
                    },
                )
            )

    return key


def get_elaborating_questions(
    project_id: str, current_prompt: str, image_id: str = None
) -> List[str]:
    res = client.responses.create(
        model="gpt-4.1-mini",
        instructions=ELABORATION_PROMPT,
        input=f"{current_prompt}",
        max_output_tokens=128,
    )
    questions_str = res.output_text
    questions = questions_str.split("\n")
    assert len(questions) > 1
    return questions


def check_elaborating_questions(
    current_prompt: str, elaborating_questions: List[str]
) -> List[str]:
    res = client.responses.create(
        model="gpt-4.1-mini",
        instructions=f"{CHECK_ELABORATION_PROMPT}\n{elaborating_questions}",
        input=f"{current_prompt}",
        max_output_tokens=128,
    )
    questions_str = res.output_text
    questions = questions_str.split("\n")

    return questions
