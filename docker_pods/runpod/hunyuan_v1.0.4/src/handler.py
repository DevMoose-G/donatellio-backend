from typing import List
from hy3dgen.shapegen.pipelines import Hunyuan3DDiTFlowMatchingPipeline
from hy3dgen.texgen import Hunyuan3DPaintPipeline
from pydantic import BaseModel
import runpod

import requests

class GenerateModelRequest(BaseModel):
    image_url: str
    presigned_urls: List[str]
    only_multiview: bool = False

cache_dir = "/workspace/hunyuan3d/cache"

shape_pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained('tencent/Hunyuan3D-2', device='cuda', cache_dir=cache_dir)
paint_pipe = Hunyuan3DPaintPipeline.from_pretrained(
    'tencent/Hunyuan3D-2-mv', 
    render_size=1024  # set your desired resolution
)
   
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

def generate_multiview(img_filepath):
    initial_mesh = shape_pipe(image=img_filepath)[0]

    # 2) Produce high-res multiview RGBs (e.g. 8 views at 512×512)
    multiviews = paint_pipe(
        image=img_filepath, 
        mesh=initial_mesh, 
        num_views=6
    ).images  # list of PIL Images at 512×512

    # Save for editing
    multiview_paths = []
    for i, view in enumerate(multiviews):
        multiview_paths.append(f'view_{i}.png')
        view.save(multiview_paths[-1])

    return multiview_paths

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
    
    if request.only_multiview:
        multiview_paths = generate_multiview("downloaded_image.png")
        errored_responses = []
        for path in multiview_paths:
            response = upload_asset(mesh_file_loc, request.presigned_urls.pop(index=0), "image/png")
            if response['status_code'] != 200:
                errored_responses.append(response)
        if len(errored_responses) > 0:
            return {
                "message": f"failed on {len(errored_responses)} uploads. Here are the error responses: {errored_responses}"
            }
    else:
        
        mesh = shape_pipe(image="downloaded_image.png")[0]
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