import PIL
import replicate
import requests

from donna_common.orm.main import AsyncSessionLocal
from donna_common.orm.master import MasterDAL
from donna_common.prompts import BASE_IMAGE_GEN_PROMPT, GEMINI_IMAGE_GEN_PROMPT
from donna_common.providers.storage import StorageProvider
from donna_common.settings import settings

STATIC_DIR = settings.static_dir


class ReplicateProvider:
    def __init__(self):
        self.storage_provider = StorageProvider()
        self.dal = MasterDAL(AsyncSessionLocal())  # figure out teardown

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
        self, image_id: str, model: str, quality: str, prompt: str
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
            "lucataco/remove-bg:95fcc2a26d3899cd6c2691c900465aaeff466285a65c14638cc5f36f34befaf1",
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

    async def edit_image(
        self,
        image_id: str,
        model: str,
        quality: str,
        prompt: str,
        parent_image_id: str,
        **kwargs,
    ):
        image_name = f"{image_id}.png"

        prompt = f"{BASE_IMAGE_GEN_PROMPT}\n{prompt}"

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
            "lucataco/remove-bg:95fcc2a26d3899cd6c2691c900465aaeff466285a65c14638cc5f36f34befaf1",
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

    async def simplify_mesh(self, mesh_id: str, ratio: float):
        s3_put_url = self.storage_provider.generate_put_url_for_mesh(
            f"{mesh_id}_simp_{int(ratio * 100)}"
        )

        replicate.run(
            "devmoose-g/mesh-retropology-asimp",
            input={"glb_file": "", "s3_url": s3_put_url, "ratio": ratio},
        )
