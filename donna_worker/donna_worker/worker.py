import asyncio

import openai

from donna_common.orm.dal.image import ImageDAL
from donna_common.orm.main import AsyncSessionLocal
from donna_common.orm.master import get_master_dal
from donna_common.providers.openai import OpenAIProvider
from donna_common.providers.replicate import ReplicateProvider
from donna_common.providers.runpod import RunpodProvider
from donna_common.redis.redisstream import RedisStream
from donna_common.redis.registry import HANDLERS, on_action
from donna_common.redis.types import ImageAction, MeshAction
from donna_worker.worker.mesh import (
    fill_static_render_images,
    generate_mesh,
    generate_texture,
)


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
        if action.function_name == "generate_image":
            # wake up geometry pipeline

            project_name = self.openai_provider.name_project(action.project_id)
            await self.runpod_service.wake_up_geometry()
            
            image_model = action.params.get("image_model")
            if image_model == "gpt4o":
                await self.openai_provider.generate_image(**action.params)
            else:
                raise Exception("HAVEN'T IMPLEMENTED THIS YET")
                await self.replicate_provider.generate_image(model=image_model, quality=action.params["quality"], prompt=action.params["prompt"])
            
            await project_name

            await self.completed_images_stream.send_msg(
                ImageAction(
                    project_id=action.project_id,
                    function_name=action.function_name,
                    params=action.params,
                    image_id=action.image_id,
                    is_partial=False,
                )
            )
        elif action.function_name == "edit_image":
            await self.runpod_service.wake_up_geometry()
            try:
                await self.openai_provider.edit_image(**action.params)
            except openai.APIError as e:
                async with AsyncSessionLocal() as session:
                    await ImageDAL(session).update_image(
                        id=action.params["image_id"], error=str(e)
                    )
            except Exception as e:
                breakpoint()
                async with AsyncSessionLocal() as session:
                    await ImageDAL(session).update_image(
                        id=action.params["image_id"], error=str(e)
                    )
            await self.completed_images_stream.send_msg(
                ImageAction(
                    project_id=action.project_id,
                    function_name=action.function_name,
                    params=action.params,
                    image_id=action.image_id,
                    is_partial=False,
                )
            )

    @on_action("mesh")
    async def handle_mesh(self, action: MeshAction):
        if action.function_name == "generate_mesh":
            mesh_ids = await generate_mesh(**action.params)
            await self.completed_meshes_stream.send_msg(
                MeshAction(
                    type="mesh",
                    params=action.params,
                    project_id=action.project_id,
                    function_name=action.function_name,
                    mesh_ids=mesh_ids,
                )
            )
        elif action.function_name == "generate_texture":
            mesh_id = await generate_texture(**action.params)
            await self.completed_meshes_stream.send_msg(
                MeshAction(
                    type="mesh",
                    project_id=action.project_id,
                    function_name=action.function_name,
                    params=action.params,
                    mesh_ids=[mesh_id],
                )
            )

    async def mainloop(self):
        await fill_static_render_images()
        await self.stream.setup_group(new_only=False)

        while True:
            messages = await self.stream.consume_msg(
                "consumer", new_only=True, n_msgs=10
            )
            if messages == []:
                print("No messages available")
                await asyncio.sleep(5)
            for msg in messages:
                print("got a message")
                handler = HANDLERS.get(msg.action.type)
                if not handler:
                    raise RuntimeError(f"Unknown action type: {msg.action.type}")
                await handler(self, msg.action)
                await self.stream.ack_msg(msg.id)


async def mainloop():
    worker = await DonnaWorker.create()
    await worker.mainloop()


if __name__ == "__main__":
    asyncio.run(mainloop())
