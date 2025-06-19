import requests
from PIL import Image

from donna_common.providers.storage import StorageProvider
from donna_common.settings import settings

PALETTES = [
    "EAE4E9",
    "FFF1E6",
    "FDE2E4",
    "FAD2E1",
    "E2ECE9",
    "BEE1E6",
    "F0EFEB",
    "DFE7FD",
    "CDDAFD",
    "CAC2F1",
]

ICON_STORAGE_KEYS = [
    "images/profileIcons/crystalIcon.png",
    "images/profileIcons/isoShapeWireframe.png",
    "images/profileIcons/planetIcon.png",
]

STATIC_DIR = settings.static_dir


def generate_profile_image_urls() -> str:
    storage_provider = StorageProvider()
    """
    Generates a profile image URL for the user based on their ID.
    The image is selected from a predefined set of icons.
    """
    for index in range(len(ICON_STORAGE_KEYS)):
        for pallete_index in range(len(PALETTES)):
            storage_key = ICON_STORAGE_KEYS[index]
            icon_url = storage_provider.generate_get_url(storage_key)
            image = Image.new("RGB", (1024, 1024), color=f"#{PALETTES[pallete_index]}")
            response = requests.get(icon_url, stream=True)
            icon_img = Image.open(response.raw).convert("RGBA")

            icon_img = icon_img.resize((750, 750))
            image.paste(
                icon_img,
                (
                    (image.width - icon_img.width) // 2,
                    (image.height - icon_img.height) // 2,
                ),
                icon_img,
            )
            image_filepath = f"{STATIC_DIR}/profile_images/{index}_{pallete_index}.png"
            image.save(image_filepath, "PNG")
            storage_key = storage_provider.upload_image(
                f"profile_images/{index}_{pallete_index}.png", image_filepath
            )
