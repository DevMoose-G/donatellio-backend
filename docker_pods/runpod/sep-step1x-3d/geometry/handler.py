from typing import List, Optional
from pydantic import BaseModel
import runpod
from step1x3d_geometry.models.pipelines.pipeline import Step1X3DGeometryPipeline
import requests
import os
from step1x3d_geometry.models.pipelines.pipeline_utils import reduce_face, remove_degenerate_face

class GenerateModelRequest(BaseModel):
    image_url: str
    presigned_urls: List[str]
    n_meshes: int = 1
    
    # use these two for finer detail & smoother meshes
    n_inference_steps: int = 50
    octree_resolution: int = 256 # 256, 384, 512, 768, 1024

    guidance_scale: float = 7.5
    max_facenum: int = 200_000

    # if you see gaps or thin bits dropped, rerun with mc_level slightly negative (e.g. -0.05).
    # if your silhouette is too bloated or fuzzy, push mc_level slightly positive (e.g. +0.02).
    # don’t exceed ±0.1 in either direction on a 2×2×2 volume
    mc_level: float = 0.0

    do_shade_smooth: bool = True

    # needs testing
    label: Optional[str] = None
    caption: Optional[str] = None

on_runpod = os.getenv("ON_RUNPOD", False)
cache_dir = "/runpod-volume/cache/step1x-3d"

if on_runpod:
    if not os.path.isdir(cache_dir):
        raise Exception(f"Cannot find cached model at {cache_dir}")

# define the pipelines
geometry_pipeline = Step1X3DGeometryPipeline.from_pretrained(cache_dir if on_runpod else "stepfun-ai/Step1X-3D", subfolder='Step1X-3D-Geometry-1300m').to("cuda")

def generate_mesh(input_image_path:str, request: GenerateModelRequest) -> str:
    # run pipeline and obtain the untextured mesh 
    out = geometry_pipeline(
        input_image_path,
        label=request.label,
        caption=request.caption,
        num_meshes_per_prompt=request.n_meshes,
        octree_resolution=request.octree_resolution,
        guidance_scale=request.guidance_scale, 
        num_inference_steps=request.n_inference_steps, 
        max_facenum=request.max_facenum,
        do_remove_degenerate_face=True,
        do_shade_smooth=request.do_shade_smooth,
        mc_level=request.mc_level
    )

    # export untextured mesh as .glb format
    untexture_mesh = remove_degenerate_face(out.mesh[0])
    untexture_mesh = reduce_face(untexture_mesh)
    return untexture_mesh

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
    
    mesh = generate_mesh("downloaded_image.png", request)
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