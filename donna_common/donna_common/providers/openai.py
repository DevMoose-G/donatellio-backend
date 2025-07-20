import base64
import os
from typing import List

import openai
import PIL.Image
import requests
from openai import OpenAI

from donna_common.orm.dal.image import ImageDAL
from donna_common.orm.dal.project import ProjectDAL
from donna_common.orm.dal.styleboard import StyleBoardDAL
from donna_common.orm.main import AsyncSessionLocal
from donna_common.prompts import (
    CHECK_ELABORATION_PROMPT,
    ELABORATION_PROMPT,
    GPT4O_IMAGE_GEN_PROMPT,
    NAME_PROJECT_BASED_ON_IMAGE,
    NAME_PROJECT_BASED_ON_PROMPT,
    STYLE_IMAGE_DESCRIPTION_PROMPT,
)
from donna_common.providers.storage import StorageProvider
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

    async def name_project(self, project_id):
        async with AsyncSessionLocal() as session:
            project_dal = ProjectDAL(session)
            project = await project_dal.get_project_by_id(project_id)
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

        async with AsyncSessionLocal() as session:
            project_dal = ProjectDAL(session)
            project = await project_dal.update_project(
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
        async with AsyncSessionLocal() as session:
            image_dal = ImageDAL(session)
            await image_dal.update_image(
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

        async with AsyncSessionLocal() as session:
            image_dal = ImageDAL(session)
            image = await image_dal.get_image_by_id(image_id)

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
                        async with AsyncSessionLocal() as session:
                            image_dal = ImageDAL(session)
                            await image_dal.update_image(
                                id=image_id, project_id=project_id, storage_key=key
                            )

                if event.type == "response.image_generation_call.completed":
                    async with AsyncSessionLocal() as session:
                        image_dal = ImageDAL(session)
                        await image_dal.update_image(
                            id=image_id, external_id=event.item_id
                        )

        except openai.APIError as e:
            # set project to be inactive
            async with AsyncSessionLocal() as session:
                project_dal = ProjectDAL(session)
                await project_dal.update_project(id=project_id, active=False)
            raise e

        await self.save_thumbnail(image_id, image_storage_key=key)

        return key

    async def is_nsfw(self, image_id=None, image_storage_key=None):
        if image_id == None and image_storage_key == None:
            raise Exception("Either image_id or image_storage_key must be provided")

        if image_storage_key == None:
            async with AsyncSessionLocal() as session:
                image_dal = ImageDAL(session)
                image = await image_dal.get_image_by_id(image_id)
            image_storage_key = image.storage_key

        response = self.client.moderations.create(
            model="omni-moderation-latest",
            input=[
                {
                    "type": "image_url",
                    "image_url": {
                        "url": self.storage_provider.generate_get_url(image_storage_key)
                    },
                }
            ],
        )

        results = response.results[0]
        if results.categories.sexual or results.categories.sexual_minors:
            return True
        if (
            results.categories.self_harm
            or results.categories.self_harm_intent
            or results.categories.self_harm_instructions
        ):
            return True
        if results.categories.violence_graphic:
            # TODO: add flag to project, but allow it to be used
            return True

        return False

    async def edit_image(
        self, image_id, project_id, parent_image_id, prompt, n, size, quality
    ) -> str:
        if prompt == "":
            raise Exception("Prompt cannot be empty")

        image_name = f"{image_id}.png"

        async with AsyncSessionLocal() as session:
            image_dal = ImageDAL(session)
            original_image = await image_dal.get_image_by_id(parent_image_id)
            
            while (
                original_image.error != None and original_image.parent_image_id is not None
            ):
                original_image = await image_dal.get_image_by_id(
                    original_image.parent_image_id
                )
        assert original_image is not None  # TODO: better error

        # TODO: get directly with aws sdk python
        if original_image.storage_key == None:
            return  # bug

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

        async with AsyncSessionLocal() as session:
            image_dal = ImageDAL(session)
            image = await image_dal.get_image_by_id(image_id)

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

            elif event.type == "response.image_generation_call.completed":
                if key != None:
                    async with AsyncSessionLocal() as session:
                        await ImageDAL(session).update_image(
                            id=image_id, external_id=event.item_id
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

        if key != None:
            await self.save_thumbnail(image_id, image_storage_key=key)

        return key

    async def generate_style_description(
        self, styleboard_id: str, image_storage_key: str
    ):
        res = self.client.responses.create(
            model="gpt-4.1",
            instructions=STYLE_IMAGE_DESCRIPTION_PROMPT,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Use the following image(s)."},
                        {
                            "type": "input_image",
                            "image_url": self.storage_provider.generate_get_url(
                                image_storage_key
                            ),
                        },
                    ],
                }
            ],
            max_output_tokens=256,
        )

        async with AsyncSessionLocal() as session:
            await StyleBoardDAL(session).update_styleboard(
                id=styleboard_id, description=res.output_text
            )

        return res.output_text

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
