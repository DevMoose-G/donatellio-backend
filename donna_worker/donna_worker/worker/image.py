import openai
from donna_common.orm.dal.image import ImageDAL
from donna_common.orm.dal.project import ProjectDAL
from donna_common.orm.dal.styleboard import StyleBoardDAL
from donna_common.orm.main import AsyncSessionLocal
from donna_common.providers.openai import OpenAIProvider
from donna_common.providers.replicate import ReplicateProvider
from donna_common.providers.runpod import RunpodProvider


openai_provider = OpenAIProvider()
runpod_service = RunpodProvider()
replicate_provider = ReplicateProvider()

async def generate_image(image_id, image_model, project_id, prompt, quality, size):
    async with AsyncSessionLocal() as session:
        project = await ProjectDAL(session).get_project_by_id(project_id)
        # check if styleboard is attached to project if so, generate description for styleboard, update it
        if project.styleboard_id:
            styleboard = await StyleBoardDAL(session).get_styleboard_by_id(
                project.styleboard_id
            )
            image_storage_key = styleboard.assets["images"][0]["storage_key"]
            prompt += (
                "\nStyle description: "
                + await openai_provider.generate_style_description(
                    project.styleboard_id, image_storage_key
                )
            )

    project_name = openai_provider.name_project(project_id)
    # wake up geometry pipeline
    await runpod_service.wake_up_geometry()

    if image_model == "gpt4o":
        await openai_provider.generate_image(
            image_id=image_id, project_id=project_id, prompt=prompt, quality=quality, n=1, size=size,
        )
    else:
        await replicate_provider.generate_image(
            image_id=image_id,
            project_id=project_id,
            model=image_model,
            quality=quality,
            prompt=prompt,
        )

    await project_name


async def edit_image(image_model, image_id, project_id, parent_image_id, prompt, quality, size, n):
    await runpod_service.wake_up_geometry()
    if image_model == "gpt4o":
        try:
            await openai_provider.edit_image(
                image_id=image_id,
                image_model=image_model,
                prompt=prompt,
                parent_image_id=parent_image_id,
                quality=quality,
                size=size,
                n=n,
            )
        except openai.APIError as e:
            async with AsyncSessionLocal() as session:
                await ImageDAL(session).update_image(
                    id=image_id, error=str(e)
                )
        except Exception as e:
            async with AsyncSessionLocal() as session:
                await ImageDAL(session).update_image(
                    id=image_id, error=str(e)
                )
    else:
        await replicate_provider.edit_image(
            model=image_model,
            image_id=image_id,
            parent_image_id=parent_image_id,
            prompt=prompt,
            quality=quality,
        )