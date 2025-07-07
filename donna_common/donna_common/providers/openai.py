import base64
import os
from typing import List

import openai
import PIL.Image
import requests
from openai import OpenAI

from donna_common.orm.dal.image import ImageDAL
from donna_common.orm.main import AsyncSessionLocal
from donna_common.orm.master import MasterDAL
from donna_common.prompts import (
    CHECK_ELABORATION_PROMPT,
    ELABORATION_PROMPT,
    GPT4O_IMAGE_GEN_PROMPT,
    NAME_PROJECT_BASED_ON_IMAGE,
    NAME_PROJECT_BASED_ON_PROMPT,
)
from donna_common.providers.storage import StorageProvider
from donna_common.redis.redisstream import RedisStream
from donna_common.redis.types import ImageAction
from donna_common.settings import settings

CURRENT_DIR = os.path.dirname(__file__)

STATIC_DIR = settings.static_dir


class OpenAIProvider:
    def __init__(self):
        # Configure OpenAI
        self.client = OpenAI(
            api_key=settings.openai_api_key,
        )
        self.storage_provider = StorageProvider()
        self.dal = MasterDAL(AsyncSessionLocal())  # figure out teardown

    async def name_project(self, project_id):
        project = await self.dal.project_dal.get_project_by_id(project_id)
        prompt = project.images[0].prompt

        user_input = {"role": "user", "content": []}

        image_get_url = None
        if prompt is not None and prompt != "Image uploaded":
            user_input["content"].append({"type": "input_text", "text": prompt})
        else:
            # send the image
            image_get_url = self.storage_provider.generate_get_url(
                project.images[0].storage_key
            )
            user_input["content"].append(
                {"type": "input_image", "image_url": image_get_url}
            )
            user_input["content"].append(
                {"type": "input_text", "text": "here is the image."}
            )

        res = self.client.responses.create(
            model="gpt-4.1-mini",
            instructions=NAME_PROJECT_BASED_ON_PROMPT
            if image_get_url is None
            else NAME_PROJECT_BASED_ON_IMAGE,
            input=[user_input],
            max_output_tokens=128,
        )
        project_name = res.output_text

        project = await self.dal.project_dal.update_project(
            id=project_id, name=project_name
        )

        return project_name

    async def save_thumbnail(self, image_id, image_storage_key):
        url = self.storage_provider.generate_get_url(image_storage_key)
        pillow_image = PIL.Image.open(requests.get(url, stream=True).raw)
        pillow_image.thumbnail((256, 256))
        pillow_image.save(f"{STATIC_DIR}/{image_id}_thumbnail.png", "PNG")
        image_filename = f"{image_id}_thumbnail.png"
        key = self.storage_provider.upload_image(
            image_filename, f"{STATIC_DIR}/{image_id}_thumbnail.png"
        )
        await self.dal.image_dal.update_image(
            id=image_id, thumbnail_image_storage_key=key
        )

    async def generate_image(
        self, image_id, project_id, prompt, n, size, quality
    ) -> str:
        if n != 1:
            n = 1

        image_name = f"{image_id}.png"

        prompt = f"{GPT4O_IMAGE_GEN_PROMPT}\n{prompt}"

        stream = self.client.responses.create(
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

        image = await self.dal.image_dal.get_image_by_id(image_id)

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

                    key = self.storage_provider.upload_image(image_name, img_filepath)

                    if image.storage_key == None:
                        await self.dal.image_dal.update_image(
                            id=image_id, project_id=project_id, storage_key=key
                        )
                    await completed_images_stream.send_msg(
                        ImageAction(
                            type="image",
                            function_name="generate_image",
                            project_id=project_id,
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
                    await self.dal.image_dal.update_image(
                        id=image_id, external_id=event.item_id
                    )
                    await completed_images_stream.send_msg(
                        ImageAction(
                            type="image",
                            function_name="generate_image",
                            project_id=project_id,
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
            # set project to be inactive
            await self.dal.project_dal.update_project(id=project_id, active=False)
            raise e
            await completed_images_stream.send_msg(
                ImageAction(
                    type="image",
                    function_name="generate_image",
                    project_id=project_id,
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

        await self.save_thumbnail(image_id, image_storage_key=key)

        await self.dal.image_dal.update_image(
            id=image_id, external_id=event.item_id
        )
        await completed_images_stream.send_msg(
            ImageAction(
                type="image",
                function_name="generate_image",
                project_id=project_id,
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

        return key

    async def edit_image(
        self, image_id, project_id, parent_image_id, prompt, n, size, quality
    ) -> str:
        if prompt == "":
            raise Exception("Prompt cannot be empty")

        image_name = f"{image_id}.png"

        original_image = await self.dal.image_dal.get_image_by_id(parent_image_id)
        while (
            original_image.error != None
            and original_image.parent_image_id is not None
        ):
            original_image = await self.dal.image_dal.get_image_by_id(
                original_image.parent_image_id
            )
        assert original_image is not None  # TODO: better error

        # TODO: get directly with aws sdk python
        if original_image.storage_key == None:
            breakpoint()  # TODO

        prompt = f"{GPT4O_IMAGE_GEN_PROMPT}\n{prompt}"

        image_input = [
            {"role": "user", "content": [{"type": "input_text", "text": prompt}]},
        ]
        # if not external_id, send the actual image
        if original_image.external_id == None:
            og_image_url = self.storage_provider.generate_get_url(
                original_image.storage_key
            )
            image_input[0]["content"].append(
                {"type": "input_image", "image_url": f"{og_image_url}"}
            )
        else:
            image_input.append(
                {"type": "image_generation_call", "id": original_image.external_id},
            )

        stream = self.client.responses.create(
            model="gpt-4.1",
            input=image_input,
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

        image = await self.dal.image_dal.get_image_by_id(image_id)

        completed_images_stream = RedisStream("completed-jobs", group_name="image")

        key = None
        
        events_debug = []
        for event in stream:
            events_debug.append(event)
            if event.type == "response.image_generation_call.partial_image":
                idx = event.partial_image_index
                image_base64 = event.partial_image_b64
                image_bytes = base64.b64decode(image_base64)

                img_filepath = f"{STATIC_DIR}/{image_id}_partial{idx}.png"
                with open(img_filepath, "wb") as f:
                    f.write(image_bytes)

                key = self.storage_provider.upload_image(image_name, img_filepath)

                if image.storage_key == None:
                    async with AsyncSessionLocal() as session:
                        await ImageDAL(session).update_image(
                            id=image_id, project_id=project_id, storage_key=key
                        )
                await completed_images_stream.send_msg(
                    ImageAction(
                        type="image",
                        function_name="edit_image",
                        project_id=project_id,
                        image_id=image_id,
                        is_partial=True,
                        params={
                            "image_id": image_id,
                            "project_id": project_id,
                            "parent_image_id": parent_image_id,
                            "prompt": prompt,
                            "n": n,
                            "size": size,
                            "quality": quality,
                        },
                    )
                )
            elif event.type == "response.image_generation_call.completed":
                if key != None:
                    async with AsyncSessionLocal() as session:
                        await ImageDAL(session).update_image(
                            id=image_id, external_id=event.item_id
                        )

                    await completed_images_stream.send_msg(
                        ImageAction(
                            type="image",
                            function_name="edit_image",
                            project_id=project_id,
                            image_id=image_id,
                            is_partial=False,
                            params={
                                "image_id": image_id,
                                "project_id": project_id,
                                "parent_image_id": parent_image_id,
                                "prompt": prompt,
                                "n": n,
                                "size": size,
                                "quality": quality,
                            },
                        )
                    )
            elif event.type == "response.completed":
                if key == None:
                    # error likely happened
                    outputs = event.response.output
                    error_msg = ""
                    for output in outputs:
                        for content in output.content:
                            if content.type == "output_text":
                                error_msg += f"{content.text} "
                    
                    if error_msg.find("safety system") != -1:
                        error_msg = "Image was blocked by safety system. Try a different prompt or a less restrictive image model."
                    
                    async with AsyncSessionLocal() as session:
                        await ImageDAL(session).update_image(
                            id=image_id, error=error_msg, storage_key=None
                        )
                    
                    await completed_images_stream.send_msg(
                        ImageAction(
                            type="image",
                            function_name="edit_image",
                            project_id=project_id,
                            image_id=image_id,
                            is_partial=False,
                            params={
                                "image_id": image_id,
                                "project_id": project_id,
                                "parent_image_id": parent_image_id,
                                "prompt": prompt,
                                "n": n,
                                "size": size,
                                "quality": quality,
                            },
                            successful=False
                        )
                    )
                
        if key != None:
            await self.save_thumbnail(image_id, image_storage_key=key)

        return key

    def get_elaborating_questions(
        self,
        project_id: str,
        current_prompt: str,
        image_id: str = None,
        n_questions: int = 3,
    ) -> List[str]:
        res = self.client.responses.create(
            model="gpt-4.1-mini",
            instructions=ELABORATION_PROMPT.format(n_questions=n_questions),
            input=f"{current_prompt}",
            max_output_tokens=128,
        )
        questions_str = res.output_text
        questions = questions_str.split("\n")
        if len(questions) == 0:
            raise Exception("No questions generated")
        return questions

    def check_elaborating_questions(
        self, current_prompt: str, elaborating_questions: List[str]
    ) -> List[str]:
        res = self.client.responses.create(
            model="gpt-4.1-mini",
            instructions=f"{CHECK_ELABORATION_PROMPT}\n{elaborating_questions}",
            input=f"{current_prompt}",
            max_output_tokens=128,
        )
        questions_str = res.output_text
        questions = questions_str.split("\n")

        return questions
