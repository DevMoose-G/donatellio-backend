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
from donna_common.redis.types import MeshAction, TexturedMeshAction
from donna_common.settings import settings

CURRENT_DIR = os.path.dirname(__file__)

STATIC_DIR = settings.static_dir

MESH_DIR = f"{STATIC_DIR}/meshes"
TEXTURE_DIR = f"{STATIC_DIR}/textures"

BLENDER_EXE = settings.blender_exe_path

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


async def render_mesh_preview_image(
    storage_key: str,
    asset_id: str,
    mesh_dal: MeshDAL = None,
    texture_dal: TextureDAL = None,
):
    storage_provider = StorageProvider()

    # download glb file
    glb_path = f"{MESH_DIR}/{asset_id}.glb"
    storage_provider.download_file(storage_key, glb_path)
    out_dir = f"{MESH_DIR}/{asset_id}"

    render_dict = run_blender_render(glb_path, out_dir)

    # crop image
    image = PIL.Image.open(render_dict["png"])
    image = crop_transparent(image)
    image.save(render_dict["png"])

    png_storage_key = storage_provider.upload_image(
        f"{asset_id}/render.png", render_dict["png"]
    )

    if mesh_dal != None:
        asset = await mesh_dal.update_mesh(
            asset_id,
            static_render_storage_key=png_storage_key,
        )
    else:
        asset = await texture_dal.update_texture(
            asset_id,
            static_render_storage_key=png_storage_key,
        )
    return asset


async def generate_mesh_formats(
    asset_id: str,
    storage_key: str,
    mesh_dal: MeshDAL = None,
    texture_dal: TextureDAL = None,
):
    storage_provider = StorageProvider()

    # download glb file
    glb_path = f"{MESH_DIR}/{asset_id}.glb"
    storage_provider.download_file(storage_key, glb_path)
    out_dir = f"{MESH_DIR}/{asset_id}"

    convert_dict = run_blender_convert(glb_path, out_dir)

    # TODO: keep in mind that there are essentially 2 copies of glbs (one in mesh_id dir and one with mesh_id.glb format)
    glb_storage_key = storage_provider.upload_mesh(
        asset_id, f"{asset_id}.glb", convert_dict["glb"]
    )

    obj_storage_key = storage_provider.upload_mesh(
        asset_id, f"{asset_id}.obj", convert_dict["obj"]
    )
    fbx_storage_key = storage_provider.upload_mesh(
        asset_id, f"{asset_id}.fbx", convert_dict["fbx"]
    )
    stl_storage_key = storage_provider.upload_mesh(
        asset_id, f"{asset_id}.stl", convert_dict["stl"]
    )
    blend_storage_key = storage_provider.upload_mesh(
        asset_id, f"{asset_id}.blend", convert_dict["blend"]
    )

    print(convert_dict["glb"])
    # breakpoint()

    if mesh_dal != None:
        asset = await mesh_dal.update_mesh(
            asset_id,
            storage_key=glb_storage_key,
            format_storage_keys={
                "obj": obj_storage_key,
                "fbx": fbx_storage_key,
                "stl": stl_storage_key,
                "blend": blend_storage_key,
            },
        )
    else:
        asset = await texture_dal.update_texture(
            asset_id,
            storage_key=glb_storage_key,
            format_storage_keys={
                "obj": obj_storage_key,
                "fbx": fbx_storage_key,
                "stl": stl_storage_key,
                "blend": blend_storage_key,
            },
        )
    return asset


async def generate_mesh(
    image_id,
    project_id,
    mesh_model: str,
    n_meshes: int,
    mesh_ids: List[str],
    quality: str,
    seed: int,
    labels: List[str],
    max_polygon_count: int,
    completed_meshes_stream,
    job_stream,
) -> List[str]:
    # call generate_mesh in runpod
    runpod_service = RunpodProvider()
    await completed_meshes_stream.send_msg(
        MeshAction(
            type="mesh",
            params={
                "image_id": image_id,
                "mesh_ids": mesh_ids,
                "project_id": project_id,
                "mesh_model": mesh_model,
                "n_meshes": n_meshes,
                "quality": quality,
                "seed": seed,
                "labels": labels,
                "max_polygon_count": max_polygon_count,
            },
            project_id=project_id,
            function_name="generate_mesh",
            mesh_ids=mesh_ids,
        )
    )
    mesh_ids = await runpod_service.generate_untextured_mesh(
        project_id,
        image_id,
        mesh_ids,
        mesh_model,
        n_meshes,
        quality,
        seed,
        labels,
        max_polygon_count,
        completed_meshes_stream,
    )

    os.makedirs(MESH_DIR, exist_ok=True)


    for mesh_id in mesh_ids:
        # perform auto-retopology on generated mesh
        # should this be a new mesh or just replace the existing mesh?
        await job_stream.send_msg(
            MeshAction(
                type="mesh",
                params={
                    "mesh_id": mesh_id,
                    "new_mesh_id": mesh_id,
                    "project_id": project_id,
                },
                project_id=project_id,
                function_name="simplify_mesh",
                mesh_ids=[mesh_id],
            )
        )

        # do i need to generate formats and render if the mesh will be simplified anyways
        # await generate_mesh_formats(mesh_id, mesh.storage_key, mesh_dal)
        # await render_mesh_preview_image(mesh.storage_key, mesh_id, mesh_dal=mesh_dal)

    return mesh_ids


async def generate_texture(
    texture_id,
    image_id,
    project_id,
    mesh_id: str,
    prompt: str,
    texture_quality: str,
    seed: int,
    completed_meshes_stream,
) -> str:
    await completed_meshes_stream.send_msg(
        TexturedMeshAction(
            type="textured_mesh",
            project_id=project_id,
            function_name="generate_texture",
            params={
                "texture_id": texture_id,
                "image_id": image_id,
                "project_id": project_id,
                "mesh_id": mesh_id,
                "prompt": prompt,
                "texture_quality": texture_quality,
                "seed": seed,
            },
            texture_id=texture_id,
        )
    )
    runpod_service = RunpodProvider()
    texture_id = await runpod_service.generate_texture_on_mesh(
        texture_id=texture_id,
        image_id=image_id,
        project_id=project_id,
        mesh_id=mesh_id,
        prompt=prompt,
        texture_quality=texture_quality,
        seed=seed,
    )

    os.makedirs(TEXTURE_DIR, exist_ok=True)

    await completed_meshes_stream.send_msg(
        TexturedMeshAction(
            type="textured_mesh",
            project_id=project_id,
            function_name="generate_texture",
            params={
                "texture_id": texture_id,
                "image_id": image_id,
                "project_id": project_id,
                "mesh_id": mesh_id,
                "prompt": prompt,
                "texture_quality": texture_quality,
                "seed": seed,
            },
            texture_id=texture_id,
        )
    )

    async with AsyncSessionLocal() as session:
        texture_dal = TextureDAL(session)

        texture = await texture_dal.get_texture_by_id(texture_id)
        # TODO: send message through websocket before converting stuff to show the user progress

        await generate_mesh_formats(
            texture_id, texture.storage_key, texture_dal=texture_dal
        )
        await render_mesh_preview_image(
            texture.storage_key, texture_id, texture_dal=texture_dal
        )

    return texture_id


async def regenerate_from_latents(
    project_id,
    old_mesh_id,
    mesh_id,
    mc_level,
    octree_resolution,
    completed_meshes_stream,
    job_stream,
    max_facenum=None,
    do_shade_smooth=True,
    n_faces=None,
) -> str:
    runpod_service = RunpodProvider()
    mesh_id = await runpod_service.regenerate_mesh_from_latents(
        project_id=project_id,
        old_mesh_id=old_mesh_id,
        mesh_id=mesh_id,
        mc_level=mc_level,
        octree_resolution=octree_resolution,
        max_facenum=max_facenum,
        do_shade_smooth=do_shade_smooth,
    )

    total_n_faces = 0
    async with AsyncSessionLocal() as session:
        mesh_dal = MeshDAL(session)
        mesh = await mesh_dal.get_mesh_by_id(mesh_id)
        total_n_faces = mesh.face_count

    if n_faces is not None:
        simplify_ratio = min(n_faces / total_n_faces, 1)
        params = {
            "simplify_ratio": simplify_ratio,
            "mesh_id": mesh_id,
            "new_mesh_id": mesh_id,
            "project_id": project_id,
        }
        # send job to simplify mesh after regen
        await job_stream.send_msg(
            MeshAction(
                project_id=project_id,
                function_name="simplify_mesh",
                params=params,
            )
        )

    os.makedirs(MESH_DIR, exist_ok=True)

    async with AsyncSessionLocal() as session:
        mesh_dal = MeshDAL(session)

        mesh = await mesh_dal.get_mesh_by_id(mesh_id)
        # send message through websocket before converting stuff to show the user progress
        await completed_meshes_stream.send_msg(
            MeshAction(
                type="mesh",
                params={
                    "old_mesh_id": old_mesh_id,
                    "mesh_id": mesh_id,
                    "project_id": project_id,
                    "mc_level": mc_level,
                    "octree_resolution": octree_resolution,
                },
                project_id=project_id,
                function_name="regenerate_from_latents",
                mesh_ids=[mesh_id],
            )
        )

        await generate_mesh_formats(mesh_id, mesh.storage_key, mesh_dal=mesh_dal)
        await render_mesh_preview_image(mesh.storage_key, mesh_id, mesh_dal=mesh_dal)
    return mesh.id


async def simplify_mesh(
    project_id, mesh_id, new_mesh_id, completed_meshes_stream, simplify_ratio=None
):
    runpod_service = RunpodProvider()
    await runpod_service.simplify_mesh(
        mesh_id, new_mesh_id, simplify_ratio=simplify_ratio
    )

    os.makedirs(MESH_DIR, exist_ok=True)

    async with AsyncSessionLocal() as session:
        mesh_dal = MeshDAL(session)

        new_mesh = await mesh_dal.get_mesh_by_id(new_mesh_id)

        # send message through websocket before converting stuff to show the user progress
        await completed_meshes_stream.send_msg(
            MeshAction(
                type="mesh",
                params={
                    "project_id": project_id,
                    "new_mesh_id": new_mesh_id,
                    "mesh_id": mesh_id,
                    "simplify_ratio": simplify_ratio,
                },
                project_id=project_id,
                function_name="simplify_mesh",
                mesh_ids=[new_mesh_id],
            )
        )

        await generate_mesh_formats(
            new_mesh_id, new_mesh.storage_key, mesh_dal=mesh_dal
        )
        await render_mesh_preview_image(
            new_mesh.storage_key, new_mesh_id, mesh_dal=mesh_dal
        )
    return new_mesh.id


async def fill_static_render_images():
    async with AsyncSessionLocal() as session:
        texture_dal = TextureDAL(session)
        mesh_dal = MeshDAL(session)

        textures = await texture_dal.get_textures_by(
            filter=(Texture.static_render_storage_key == None)
            & (Texture.storage_key != None)
        )
        for texture in textures:
            if texture.storage_key == None:
                continue
            await render_mesh_preview_image(
                texture.storage_key, texture.id, texture_dal=texture_dal
            )

        meshes = await mesh_dal.get_meshes_by(
            filter=(Mesh.static_render_storage_key == None) & (Mesh.storage_key != None)
        )
        for mesh in meshes:
            if mesh.storage_key == None:
                continue
            await render_mesh_preview_image(
                mesh.storage_key, mesh.id, mesh_dal=mesh_dal
            )


async def fill_other_formats():
    async with AsyncSessionLocal() as session:
        texture_dal = TextureDAL(session)
        mesh_dal = MeshDAL(session)

        textures = await texture_dal.get_textures_by(
            Texture.format_storage_keys == None
        )
        for texture in textures:
            if texture.storage_key == None:
                continue
            await generate_mesh_formats(
                texture.id, texture.storage_key, texture_dal=texture_dal
            )

        meshes = await mesh_dal.get_meshes_by(Mesh.format_storage_keys == None)
        for mesh in meshes:
            if mesh.storage_key == None:
                continue
            await generate_mesh_formats(mesh.id, mesh.storage_key, mesh_dal=mesh_dal)


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
        if line.strip().startswith("GLB:"):
            result["glb"] = line.split("GLB:")[1].strip()
        elif line.strip().startswith("OBJ:"):
            result["obj"] = line.split("OBJ:")[1].strip()
        elif line.strip().startswith("FBX:"):
            result["fbx"] = line.split("FBX:")[1].strip()
        elif line.strip().startswith("STL:"):
            result["stl"] = line.split("STL:")[1].strip()
        elif line.strip().startswith("Blend:"):
            result["blend"] = line.split("Blend:")[1].strip()

    if result == {}:
        err = proc.stderr
        raise RuntimeError(f"Blender export failed: {err}")

    # Validate that each file actually exists
    for key, path in result.items():
        if not os.path.isfile(path):
            raise RuntimeError(f"Expected output {key} was not created: {path}")

    return result


def run_blender_render(glb_path, out_dir, clear_texture=False) -> Dict[str, str]:
    if os.path.isabs(glb_path) == False:
        glb_path = os.path.abspath(glb_path)
    if os.path.isabs(out_dir) == False:
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
        if path is None or not os.path.isfile(path):
            raise RuntimeError(
                f"Output: \n{proc.stdout}\n\nExpected output {key} was not created: {path}"
            )

    return result
