import asyncio
import os

import openai

from donna_common.orm.dal.image import ImageDAL
from donna_common.orm.dal.project import ProjectDAL
from donna_common.orm.dal.styleboard import StyleBoardDAL
from donna_common.orm.main import AsyncSessionLocal
from donna_common.orm.master import get_master_dal
from donna_common.providers.openai import OpenAIProvider
from donna_common.providers.replicate import ReplicateProvider
from donna_common.providers.runpod import RunpodProvider
from donna_common.redis.redisstream import RedisStream
from donna_common.redis.registry import HANDLERS, on_action
from donna_common.redis.types import (
    ImageAction,
    MeshAction,
    RedisMessage,
    TexturedMeshAction,
)
from donna_common.settings import settings
from donna_worker.worker.mesh import (
    fill_other_formats,
    fill_static_render_images,
    generate_mesh,
    generate_texture,
    regenerate_from_latents,
    simplify_mesh,
)

MESH_PATH = f"{settings.static_dir}/meshes"


class DonnaWorker:
    def __init__(self):
        self.session = AsyncSessionLocal()

        self.openai_provider = OpenAIProvider()
        self.runpod_service = RunpodProvider()
        self.replicate_provider = ReplicateProvider()

        self.stream = RedisStream("requested-jobs")
        self.completed_images_stream = RedisStream("completed-jobs", group_name="image")
        self.completed_meshes_stream = RedisStream("completed-jobs", group_name="mesh")

    @classmethod
    async def create(cls):
        self = cls()
        await self.stream.setup_group(new_only=False)
        self.master_dal = await get_master_dal(self.session)
        return self

    @on_action("image")
    async def handle_image(self, action: ImageAction):
        func_params = action.params.copy()

        image_model = func_params.pop("image_model", None)
        if action.function_name == "generate_image":
            async with AsyncSessionLocal() as session:
                project = await ProjectDAL(session).get_project_by_id(action.project_id)
                # check if styleboard is attached to project if so, generate description for styleboard, update it
                if project.styleboard_id:
                    styleboard = await StyleBoardDAL(session).get_styleboard_by_id(
                        project.styleboard_id
                    )
                    image_storage_key = styleboard.assets["images"][0]["storage_key"]
                    func_params["prompt"] += (
                        "\nStyle description: "
                        + await self.openai_provider.generate_style_description(
                            project.styleboard_id, image_storage_key
                        )
                    )

            project_name = self.openai_provider.name_project(action.project_id)
            # wake up geometry pipeline
            await self.runpod_service.wake_up_geometry()

            if image_model == "gpt4o":
                await self.openai_provider.generate_image(**func_params, completed_images_stream=self.completed_images_stream)
            else:
                await self.replicate_provider.generate_image(
                    image_id=func_params["image_id"],
                    project_id=action.project_id,
                    model=image_model,
                    quality=func_params["quality"],
                    prompt=func_params["prompt"],
                    completed_images_stream=self.completed_images_stream,
                )

            await project_name

            await self.completed_images_stream.send_msg(
                ImageAction(
                    project_id=action.project_id,
                    function_name=action.function_name,
                    params=action.params,
                    image_id=action.params["image_id"],
                    is_partial=False,
                )
            )
        elif action.function_name == "edit_image":
            await self.runpod_service.wake_up_geometry()
            if image_model == "gpt4o":
                try:
                    await self.openai_provider.edit_image(**func_params)
                except openai.APIError as e:
                    async with AsyncSessionLocal() as session:
                        await ImageDAL(session).update_image(
                            id=action.params["image_id"], error=str(e)
                        )
                except Exception as e:
                    async with AsyncSessionLocal() as session:
                        await ImageDAL(session).update_image(
                            id=action.params["image_id"], error=str(e)
                        )
            else:
                await self.replicate_provider.edit_image(
                    model=image_model, **func_params
                )

            await self.completed_images_stream.send_msg(
                ImageAction(
                    project_id=action.project_id,
                    function_name=action.function_name,
                    params=action.params,
                    image_id=action.params["image_id"],
                    is_partial=False,
                )
            )

    @on_action("mesh")
    async def handle_mesh(self, action: MeshAction):
        print("Got mesh action:", action)
        if action.function_name == "generate_mesh":
            mesh_ids = await generate_mesh(
                **action.params,
                completed_meshes_stream=self.completed_meshes_stream,
                job_stream=self.stream,
            )

        elif action.function_name == "regenerate_from_latents":
            mesh_id = await regenerate_from_latents(
                **action.params,
                completed_meshes_stream=self.completed_meshes_stream,
                job_stream=self.stream,
            )
            mesh_ids = [mesh_id]

        elif action.function_name == "simplify_mesh":
            print("Calling runpod deployment to simplify the mesh")
            mesh_id = await simplify_mesh(
                **action.params, completed_meshes_stream=self.completed_meshes_stream
            )
            mesh_ids = [mesh_id]

        await self.completed_meshes_stream.send_msg(
            MeshAction(
                type="mesh",
                params=action.params,
                project_id=action.project_id,
                function_name=action.function_name,
                mesh_ids=mesh_ids,
            )
        )

    @on_action("textured_mesh")
    async def handle_textured_mesh(self, action: TexturedMeshAction):
        if action.function_name == "generate_texture":
            texture_id = await generate_texture(
                **action.params, completed_meshes_stream=self.completed_meshes_stream
            )
            await self.completed_meshes_stream.send_msg(
                TexturedMeshAction(
                    type="textured_mesh",
                    project_id=action.project_id,
                    function_name=action.function_name,
                    params=action.params,
                    texture_id=texture_id,
                )
            )

    async def mainloop(self):
        # generate_profile_image_urls()

        os.makedirs(MESH_PATH, exist_ok=True)

        await fill_other_formats()
        await fill_static_render_images()

        await self.stream.setup_group(new_only=False)

        for i in range(10):
            while True:
                messages = await self.stream.consume_msg(
                    f"consumer-{i}", new_only=True, n_msgs=10
                )
                if messages == []:
                    print("No messages available")
                    await asyncio.sleep(2)
                for msg in messages:
                    print("got a message")
                    handler = HANDLERS.get(msg.action.type)
                    if not handler:
                        raise RuntimeError(f"Unknown action type: {msg.action.type}")

                    async def process_message(msg: RedisMessage):
                        action = msg.action.model_copy()
                        try:
                            await handler(self, msg.action)
                        except Exception as e:
                            print(f"Error processing message: {e}. On attempt {action.attempts}.")
                            # resend the message if attempt count < 3 and increase attempt count
                            if action.attempts < 3:
                                print("Resending message")
                                action.attempts += 1
                                await self.stream.send_msg(
                                    action
                                )
                        await self.stream.ack_msg(msg.id)

                    asyncio.create_task(process_message(msg))


# TODO: increase # of concurrent workers
async def mainloop():
    worker = await DonnaWorker.create()
    await worker.mainloop()


if __name__ == "__main__":
    asyncio.run(mainloop())
