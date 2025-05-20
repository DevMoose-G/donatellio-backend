from typing import List
from pydantic import BaseModel
import runpod
import requests
import os
from step1x3d_texture.pipelines.step1x_3d_texture_synthesis_pipeline import (
    Step1X3DTexturePipeline,
)
from trimesh import load
from step1x3d_texture.pipelines.pipeline_utils import reduce_face, remove_degenerate_face


class GenerateTextureRequest(BaseModel):
    mesh_url: str
    image_url: str
    presigned_urls: List[str]

on_runpod = os.getenv("ON_RUNPOD", False)
cache_dir = "/runpod-volume/cache/step1x-3d"

if on_runpod:
    if not os.path.isdir(cache_dir):
        raise Exception(f"Cannot find cached model at {cache_dir}")

# define the pipelines
texture_pipeline = Step1X3DTexturePipeline.from_pretrained(cache_dir if on_runpod else "stepfun-ai/Step1X-3D" , subfolder="Step1X-3D-Texture")


def generate_textured_mesh(untexture_mesh_path, input_image_path):
    untexture_mesh = load(untexture_mesh_path)
    
    untexture_mesh = remove_degenerate_face(untexture_mesh)
    untexture_mesh = reduce_face(untexture_mesh)

    # texture mapping
    textured_mesh = texture_pipeline(input_image_path, untexture_mesh)

    return textured_mesh

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
    request: GenerateTextureRequest = GenerateTextureRequest(**event['input'])

    # Send a GET request to the mesh URL
    response = requests.get(request.mesh_url)

    # Check if the request was successful
    if response.status_code == 200:
        with open("downloaded_mesh.glb", "wb") as file:
            file.write(response.content)  # Write the content of the mesh
        print("Mesh downloaded successfully.")
    else:
        return {
            "message":"cannot download mesh",
            "status_code":404
        }
    
    response = requests.get(request.image_url)
    
    if response.status_code == 200:
        with open("downloaded_image.png", "wb") as file:
            file.write(response.content)  # Write the content of the mesh
        print("Image downloaded successfully.")
    else:
        return {
            "message":"cannot download image",
            "status_code":404
        }
    
    mesh = generate_textured_mesh("downloaded_mesh.glb", "downloaded_image.png")
    # export textured mesh as .glb format
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