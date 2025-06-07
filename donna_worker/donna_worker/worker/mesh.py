import os
import subprocess
from pathlib import Path
from typing import Dict, List

import PIL.Image
from openai import OpenAI

from donna_common.orm.dal.mesh import MeshDAL
from donna_common.orm.dal.texture import TextureDAL
from donna_common.orm.main import AsyncSessionLocal
from donna_common.orm.models.mesh import Mesh
from donna_common.orm.models.texture import Texture
from donna_common.providers.runpod import RunpodProvider
from donna_common.providers.storage import StorageProvider
from donna_common.settings import settings

CURRENT_DIR = os.path.dirname(__file__)

STATIC_DIR = settings.static_dir

MESH_DIR = f"{STATIC_DIR}/meshes"
TEXTURE_DIR = f"{STATIC_DIR}/textures"

BLENDER_EXE = f"C:/Program Files/Blender Foundation/Blender 4.3/blender.exe"

# Configure OpenAI
client = OpenAI(
    api_key=settings.openai_api_key,
)


def crop_transparent(im):
    """
    Crop an RGBA image to the minimal bounding box of non-transparent pixels.
    Returns a new PIL.Image.
    """
    if im.mode != "RGBA":
        raise ValueError("Image must have an alpha channel (mode='RGBA').")

    # Extract alpha channel and find bounding box of non-zero alpha
    alpha = im.split()[-1]
    bbox = alpha.getbbox()
    if bbox:
        return im.crop(bbox)
    else:
        # Entire image is fully transparent—return as-is (or handle differently)
        return im.copy()


async def generate_mesh(
    image_id,
    project_id,
    mesh_model: str,
    n_meshes: int,
    quality: str,
    seed: int,
    labels: List[str],
    max_polygon_count: int,
) -> List[str]:

    # call generate_mesh in runpod
    runpod_service = RunpodProvider()
    mesh_ids = await runpod_service.generate_untextured_mesh(
        project_id,
        image_id,
        mesh_model,
        n_meshes,
        quality,
        seed,
        labels,
        max_polygon_count,
    )

    os.makedirs(MESH_DIR, exist_ok=True)

    async with AsyncSessionLocal() as session:
        mesh_dal = MeshDAL(session)

        for mesh_id in mesh_ids:
            mesh = await mesh_dal.get_mesh_by_id(mesh_id)
            storage_provider = StorageProvider()

            # download glb file
            glb_path = f"{MESH_DIR}/{mesh_id}.glb"
            storage_provider.download_file(mesh.storage_key, glb_path)
            out_dir = f"{MESH_DIR}/{mesh_id}"

            render_dict = run_blender_render(glb_path, out_dir)

            png_storage_key = storage_provider.upload_image(
                f"{mesh_id}/render.png", render_dict["png"]
            )

            convert_dict = run_blender_convert(glb_path, out_dir)
            obj_storage_key = storage_provider.upload_mesh(
                mesh_id, f"{mesh_id}.obj", convert_dict["obj"]
            )
            fbx_storage_key = storage_provider.upload_mesh(
                mesh_id, f"{mesh_id}.fbx", convert_dict["fbx"]
            )
            stl_storage_key = storage_provider.upload_mesh(
                mesh_id, f"{mesh_id}.stl", convert_dict["stl"]
            )
            blend_storage_key = storage_provider.upload_mesh(
                mesh_id, f"{mesh_id}.blend", convert_dict["blend"]
            )

            mesh = await mesh_dal.update_mesh(
                mesh_id,
                static_render_storage_key=png_storage_key,
                format_storage_keys={
                    "obj": obj_storage_key,
                    "fbx": fbx_storage_key,
                    "stl": stl_storage_key,
                    "blend": blend_storage_key,
                },
            )

    return mesh_ids


async def generate_texture(
    image_id, project_id, mesh_id: str, prompt: str, texture_quality: str, seed: int
) -> str:
    runpod_service = RunpodProvider()
    texture_id = await runpod_service.generate_texture_on_mesh(
        image_id=image_id,
        project_id=project_id,
        mesh_id=mesh_id,
        prompt=prompt,
        texture_quality=texture_quality,
        seed=seed,
    )

    os.makedirs(TEXTURE_DIR, exist_ok=True)

    async with AsyncSessionLocal() as session:
        texture_dal = TextureDAL(session)

        texture = await texture_dal.get_texture_by_id(texture_id)
        storage_provider = StorageProvider()

        # download glb file
        glb_path = f"{TEXTURE_DIR}/{texture_id}.glb"
        storage_provider.download_file(texture.storage_key, glb_path)
        out_dir = f"{TEXTURE_DIR}/{mesh_id}"

        render_dict = run_blender_render(glb_path, out_dir)
        png_storage_key = storage_provider.upload_image(
            f"{texture_id}/render.png", render_dict["png"]
        )

        convert_dict = run_blender_convert(glb_path, out_dir)
        obj_storage_key = storage_provider.upload_mesh(
            texture_id, f"{texture_id}.obj", convert_dict["obj"]
        )
        fbx_storage_key = storage_provider.upload_mesh(
            texture_id, f"{texture_id}.fbx", convert_dict["fbx"]
        )
        stl_storage_key = storage_provider.upload_mesh(
            texture_id, f"{texture_id}.stl", convert_dict["stl"]
        )
        blend_storage_key = storage_provider.upload_mesh(
            texture_id, f"{texture_id}.blend", convert_dict["blend"]
        )

        texture = await texture_dal.update_texture(
            texture_id,
            static_render_storage_key=png_storage_key,
            format_storage_keys={
                "obj": obj_storage_key,
                "fbx": fbx_storage_key,
                "stl": stl_storage_key,
                "blend": blend_storage_key,
            },
        )

    return texture_id


async def fill_static_render_images():
    async with AsyncSessionLocal() as session:
        texture_dal = TextureDAL(session)
        mesh_dal = MeshDAL(session)
        storage_provider = StorageProvider()

        textures = await texture_dal.get_textures_by(
            Texture.static_render_storage_key == None
        )
        for texture in textures:
            glb_path = f"{TEXTURE_DIR}/{texture.id}.glb"
            storage_provider.download_file(texture.storage_key, glb_path)
            out_dir = f"{TEXTURE_DIR}/{texture.id}"
            render_dict = run_blender_render(glb_path, out_dir)

            # crop image
            image = PIL.Image.open(render_dict["png"])
            image = crop_transparent(image)
            image.save(render_dict["png"])

            png_storage_key = storage_provider.upload_image(
                f"{texture.id}/render.png", render_dict["png"]
            )
            await texture_dal.update_texture(
                texture.id, static_render_storage_key=png_storage_key
            )

        meshes = await mesh_dal.get_meshes_by(Mesh.static_render_storage_key == None)
        for mesh in meshes:
            glb_path = f"{MESH_DIR}/{mesh.id}.glb"
            storage_provider.download_file(mesh.storage_key, glb_path)
            out_dir = f"{MESH_DIR}/{mesh.id}"
            render_dict = run_blender_render(glb_path, out_dir)

            # crop image
            image = PIL.Image.open(render_dict["png"])
            image = crop_transparent(image)
            image.save(render_dict["png"])

            png_storage_key = storage_provider.upload_image(
                f"{mesh.id}/render.png", render_dict["png"]
            )
            await mesh_dal.update_mesh(
                mesh.id, static_render_storage_key=png_storage_key
            )


async def fill_other_formats():
    async with AsyncSessionLocal() as session:
        texture_dal = TextureDAL(session)
        mesh_dal = MeshDAL(session)
        storage_provider = StorageProvider()

        textures = await texture_dal.get_textures_by(
            Texture.format_storage_keys == None
        )
        for texture in textures:
            glb_path = f"{TEXTURE_DIR}/{texture.id}.glb"
            storage_provider.download_file(texture.storage_key, glb_path)
            out_dir = f"{TEXTURE_DIR}/{texture.id}"
            convert_dict = run_blender_convert(glb_path, out_dir)

            obj_key = storage_provider.upload_mesh(
                texture.id, f"{texture.id}.obj", convert_dict["obj"]
            )
            fbx_key = storage_provider.upload_mesh(
                texture.id, f"{texture.id}.fbx", convert_dict["fbx"]
            )
            stl_key = storage_provider.upload_mesh(
                texture.id, f"{texture.id}.stl", convert_dict["stl"]
            )
            blend_key = storage_provider.upload_mesh(
                texture.id, f"{texture.id}.blend", convert_dict["blend"]
            )

            await texture_dal.update_texture(
                texture.id,
                format_storage_keys={
                    "obj": obj_key,
                    "fbx": fbx_key,
                    "stl": stl_key,
                    "blend": blend_key,
                },
            )

        meshes = await mesh_dal.get_meshes_by(Mesh.format_storage_keys == None)
        for mesh in meshes:
            glb_path = f"{MESH_DIR}/{mesh.id}.glb"
            storage_provider.download_file(mesh.storage_key, glb_path)
            out_dir = f"{MESH_DIR}/{mesh.id}"
            convert_dict = run_blender_convert(glb_path, out_dir)
            obj_key = storage_provider.upload_mesh(
                mesh.id, f"{mesh.id}.obj", convert_dict["obj"]
            )
            fbx_key = storage_provider.upload_mesh(
                mesh.id, f"{mesh.id}.fbx", convert_dict["fbx"]
            )
            stl_key = storage_provider.upload_mesh(
                mesh.id, f"{mesh.id}.stl", convert_dict["stl"]
            )
            blend_key = storage_provider.upload_mesh(
                mesh.id, f"{mesh.id}.blend", convert_dict["blend"]
            )

            await mesh_dal.update_mesh(
                mesh.id,
                format_storage_keys={
                    "obj": obj_key,
                    "fbx": fbx_key,
                    "stl": stl_key,
                    "blend": blend_key,
                },
            )


def run_blender_convert(glb_path: str, out_dir: str) -> Dict[str, str]:
    """
    Spawns a Blender process in background to convert the glb at glb_path
    into OBJ, FBX, STL, and .blend under out_dir.
    Returns a dict of { "obj": ..., "fbx": ..., ... } on success,
    or raises an exception on error.
    """
    glb_path = os.path.abspath(glb_path)
    out_dir = os.path.abspath(out_dir)

    # Ensure input file exists
    if not os.path.isfile(glb_path):
        raise FileNotFoundError(f"GLB file not found: {glb_path}")

    # Ensure output directory exists
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    # Build the Blender command:
    #   blender --background --python convert_script.py -- <glb_path> <out_dir>
    script_path = os.path.join(CURRENT_DIR, "../blender/blender_scripts/convert.py")
    if not os.path.isfile(script_path):
        raise FileNotFoundError(f"Converter script not found: {script_path}")

    cmd = [
        BLENDER_EXE,
        "--background",
        "--python",
        script_path,
        "--",  # everything after -- goes to our script
        glb_path,
        out_dir,
    ]

    # Run the process and capture stdout/stderr
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = proc.stderr or proc.stdout
        raise RuntimeError(f"Blender export failed: {err}")

    # On success, our script prints the output paths to stdout
    # For simplicity, parse the printed lines:
    result = {}
    for line in proc.stdout.splitlines():
        if line.strip().startswith("OBJ:"):
            result["obj"] = line.split("OBJ:")[1].strip()
        elif line.strip().startswith("FBX:"):
            result["fbx"] = line.split("FBX:")[1].strip()
        elif line.strip().startswith("STL:"):
            result["stl"] = line.split("STL:")[1].strip()
        elif line.strip().startswith("Blend:"):
            result["blend"] = line.split("Blend:")[1].strip()

    # Validate that each file actually exists
    for key, path in result.items():
        if not os.path.isfile(path):
            raise RuntimeError(f"Expected output {key} was not created: {path}")

    return result


def run_blender_render(glb_path, out_dir, clear_texture=False) -> Dict[str, str]:
    glb_path = os.path.abspath(glb_path)
    out_dir = os.path.abspath(out_dir)

    # Ensure input file exists
    if not os.path.isfile(glb_path):
        raise FileNotFoundError(f"GLB file not found: {glb_path}")

    # Ensure output directory exists
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    if clear_texture == True:
        clear_texture = "true"
    else:
        clear_texture = "false"

    # Build the Blender command:
    #   blender --background --python render.py -- <glb_path> <out_dir> <clear_texture>
    script_path = os.path.join(CURRENT_DIR, "../blender/blender_scripts/render.py")
    if not os.path.isfile(script_path):
        raise FileNotFoundError(f"Converter script not found: {script_path}")

    cmd = [
        BLENDER_EXE,
        "--background",
        "--python",
        script_path,
        "--",  # everything after -- goes to our script
        glb_path,
        out_dir,
        clear_texture,
    ]

    # Run the process and capture stdout/stderr
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = proc.stderr or proc.stdout
        raise RuntimeError(f"Blender export failed: {err}")
    # On success, our script prints the output paths to stdout
    # For simplicity, parse the printed lines:
    result = {"png": None}
    for line in proc.stdout.splitlines():
        if line.strip().startswith("PNG:"):
            result["png"] = line.split("PNG:")[1].strip()

    # Validate that each file actually exists
    for key, path in result.items():
        if not os.path.isfile(path):
            raise RuntimeError(f"Expected output {key} was not created: {path}")

    return result
