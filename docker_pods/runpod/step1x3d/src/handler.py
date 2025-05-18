from typing import List
from pydantic import BaseModel
import runpod
from step1x3d_geometry.models.pipelines.pipeline import Step1X3DGeometryPipeline
import torch
import requests

class GenerateModelRequest(BaseModel):
    image_url: str
    presigned_urls: List[str]
    only_multiview: bool = False

from step1x3d_texture.pipelines.step1x_3d_texture_synthesis_pipeline import (
    Step1X3DTexturePipeline,
)
from step1x3d_geometry.models.pipelines.pipeline_utils import reduce_face, remove_degenerate_face
import trimesh

on_runpod = os.getenv("ON_RUNPOD", False)
cache_dir = "/workspace/cache/step1x-3d"

# define the pipelines
geometry_pipeline = Step1X3DGeometryPipeline.from_pretrained(cache_dir if on_runpod else "stepfun-ai/Step1X-3D", subfolder='Step1X-3D-Geometry-1300m').to("cuda")
texture_pipeline = Step1X3DTexturePipeline.from_pretrained(cache_dir if on_runpod else "stepfun-ai/Step1X-3D" , subfolder="Step1X-3D-Texture")

def generate_textured_mesh(untexture_mesh_path, input_image_path) -> str:
    untexture_mesh = trimesh.load(untexture_mesh_path)

    untexture_mesh = remove_degenerate_face(untexture_mesh)
    untexture_mesh = reduce_face(untexture_mesh)

    # texture mapping
    textured_mesh = texture_pipeline(input_image_path, untexture_mesh)

    # export textured mesh as .glb format
    return textured_mesh

def generate_mesh(input_image_path) -> str:
    # run pipeline and obtain the untextured mesh 
    generator = torch.Generator(device=geometry_pipeline.device).manual_seed(2025)
    out = geometry_pipeline(input_image_path, guidance_scale=7.5, num_inference_steps=50)

    # export untextured mesh as .glb format
    out.mesh[0].export("untexture_mesh.glb")
    
    return generate_textured_mesh("untexture_mesh.glb", input_image_path)

def random_string(length: int) -> str:
    import secrets
    import string
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))

def upload_asset(file_loc, presigned_url, content_type):
    try:
        with open(file_loc, "rb") as f:
            resp = requests.put(
                presigned_url,
                data=f,
                headers={"Content-Type": content_type}
            )
        
        if resp.status_code != 200:
            return {
                "message":f"cannot upload glb file. Response Code: {resp.status_code}. Response: {resp.text}",
                "status_code":404
            }
    except Exception as e:
        return {
            "message":f"cannot upload glb file. {e}",
            "status_code":404
        }

    return {
        "status_code":200
    }

def handler(event):
    request: GenerateModelRequest = GenerateModelRequest(**event['input'])

    # Send a GET request to the image URL
    response = requests.get(request.image_url)

    # Check if the request was successful
    if response.status_code == 200:
        with open("downloaded_image.png", "wb") as file:
            file.write(response.content)  # Write the content of the image
        print("Image downloaded successfully.")
    else:
        return {
            "message":"cannot download image",
            "status_code":404
        }

    # rembg = BackgroundRemover()
    # image = rembg(image)
    
    if request.only_multiview:
        raise Exception("Unsupported for step1x-3d")
        multiview_paths = generate_multiview("downloaded_image.png")
        errored_responses = []
        for i, path in enumerate(multiview_paths):
            response = upload_asset(path, request.presigned_urls[i], "image/png")
            if response['status_code'] != 200:
                errored_responses.append(response)
        if len(errored_responses) > 0:
            return {
                "message": f"failed on {len(errored_responses)} uploads. Here are the error responses: {errored_responses}"
            }
    else:
        
        mesh = generate_mesh("downloaded_image.png")
        mesh_file_loc = f"mesh{random_string(16)}.glb"
        mesh.export(mesh_file_loc)

        response = upload_asset(mesh_file_loc, request.presigned_urls[0], "model/gltf-binary")
        if response['status_code'] != 200:
            return response

    return {
        "message":f"success. File uploaded to {request.presigned_urls}",
        "status_code":200
    }

if __name__ == '__main__':
    runpod.serverless.start({'handler': handler })