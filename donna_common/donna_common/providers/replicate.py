import PIL
import replicate
import requests

from donna_common.orm.main import AsyncSessionLocal
from donna_common.orm.master import MasterDAL
from donna_common.prompts import (
    GEMINI_IMAGE_GEN_PROMPT,
    KLING_VIDEO_MV_NEGATIVE_PROMPT,
    KLING_VIDEO_MV_PROMPT,
    REPLICATE_IMAGE_EDIT_PROMPT,
)
from donna_common.providers.storage import StorageProvider
from donna_common.redis.types import ImageAction
from donna_common.settings import settings
from donna_common.utils.multiview import extract_frames

STATIC_DIR = settings.static_dir


class ReplicateProvider:
    def __init__(self):
        self.storage_provider = StorageProvider()
        self.dal = MasterDAL(AsyncSessionLocal())  # figure out teardown

        self.blackforest_headers = {
            "x-key": settings.black_forest_api_token,
            "Content-Type": "application/json",
        }

    # copied from OpenAIProvider
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
        self, project_id: str, image_id: str, model: str, quality: str, prompt: str, completed_images_stream
    ) -> str:
        image_name = f"{image_id}.png"

        prompt = f"{GEMINI_IMAGE_GEN_PROMPT}\n{prompt}"

        image_model = ""
        input_data = {"prompt": prompt}
        if model == "fluxkontext":
            if quality == "high":
                image_model = "black-forest-labs/flux-kontext-max"

            else:
                image_model = "black-forest-labs/flux-kontext-pro"

            input_data["aspect_ratio"] = "1:1"
            # input_data['safety_tolerance'] = 6 # most permissive

        elif model == "imagen4":
            if quality == "high":
                image_model = "google/imagen-4-ultra"
            elif quality == "medium":
                image_model = "google/imagen-4"
            elif quality == "low":
                image_model = "google/imagen-4-fast"

            input_data["aspect_ratio"] = "1:1"
            input_data["safety_tolerance"] = "block_only_high"
        else:
            raise ValueError("Unsupported model or quality")

        input_data["output_format"] = "png"

        output = replicate.run(image_model, input=input_data)

        image = await self.dal.image_dal.get_image_by_id(image_id)

        # Save the generated image
        output_path = f"{STATIC_DIR}/{image_name}"
        with open(output_path, "wb") as f:
            f.write(output.read())

        # save to storage
        key = self.storage_provider.upload_image(image_name, output_path)

        if image.storage_key == None:
            await self.dal.image_dal.update_image(id=image_id, storage_key=key)

        image_url = self.storage_provider.generate_get_url(key)

        # remove the background
        output = replicate.run(
            "851-labs/background-remover:a029dff38972b5fda4ec5d75d7d1cd25aeff621d2cf4946a41055d7db66b80bc",
            input={"image": image_url},
        )

        # Save the image with background removed
        with open(output_path, "wb") as f:
            f.write(output.read())

        # save to storage
        key = self.storage_provider.upload_image(image_name, output_path)

        await self.save_thumbnail(image_id, image_storage_key=key)

        return output

    async def edit_image(
        self,
        image_id: str,
        model: str,
        quality: str,
        prompt: str,
        parent_image_id: str,
    ):
        image_name = f"{image_id}.png"

        prompt = f"{REPLICATE_IMAGE_EDIT_PROMPT}\n{prompt}"

        image_model = ""
        input_data = {"prompt": prompt}
        if model == "fluxkontext":
            if quality == "high":
                image_model = "black-forest-labs/flux-kontext-max"

            else:
                image_model = "black-forest-labs/flux-kontext-pro"

            input_data["aspect_ratio"] = "1:1"
            input_data["safety_tolerance"] = (
                6  # TEMP: most permissive (TODO: check if this is too low)
            )
        else:
            raise ValueError("Unsupported model")

        original_image = await self.dal.image_dal.get_image_by_id(parent_image_id)
        original_image_url = self.storage_provider.generate_get_url(
            original_image.storage_key
        )
        input_data["input_image"] = original_image_url

        input_data["output_format"] = "png"

        output = replicate.run(image_model, input=input_data)

        image = await self.dal.image_dal.get_image_by_id(image_id)

        # Save the generated image
        output_path = f"{STATIC_DIR}/{image_name}"
        with open(output_path, "wb") as f:
            f.write(output.read())

        # save to storage
        key = self.storage_provider.upload_image(image_name, output_path)

        if image.storage_key == None:
            await self.dal.image_dal.update_image(id=image_id, storage_key=key)

        image_url = self.storage_provider.generate_get_url(key)

        # remove the background
        output = replicate.run(
            "851-labs/background-remover:a029dff38972b5fda4ec5d75d7d1cd25aeff621d2cf4946a41055d7db66b80bc",
            input={"image": image_url},
        )

        # Save the image with background removed
        with open(output_path, "wb") as f:
            f.write(output.read())

        # save to storage
        key = self.storage_provider.upload_image(image_name, output_path)

        # TODO: add the completed streams part

        await self.save_thumbnail(image_id, image_storage_key=key)

        return output

    async def generate_multiviews(self, image_id):
        image = await self.dal.image_dal.get_image_by_id(image_id)
        image_url = self.storage_provider.generate_get_url(image.storage_key)
        input_data = {
            "start_image": image_url,
            "prompt": KLING_VIDEO_MV_PROMPT,
            "negative_prompt": KLING_VIDEO_MV_NEGATIVE_PROMPT,
            "duration": 5,
        }

        output = replicate.run("kwaivgi/kling-v2.1", input=input_data)

        output_path = f"{STATIC_DIR}/{image_id}_mv.mp4"
        with open(output_path, "wb") as file:
            file.write(output.read())

        frame_paths = extract_frames(output_path, f"{STATIC_DIR}/{image_id}_mv")

        # upload all the frames in a single folder in s3 and save that folder's key in db
        mv_storage_key = f"{image_id}_mv"
        for i, frame_path in enumerate(frame_paths):
            self.storage_provider.upload_image(
                f"{mv_storage_key}/frame_{i}.png", frame_path
            )
        mv_storage_key = f"images/{mv_storage_key}"
        await self.dal.image_dal.update_image(
            id=image_id, multiview_image_dir=mv_storage_key
        )
