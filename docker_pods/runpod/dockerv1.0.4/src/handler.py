from hy3dgen.shapegen.pipelines import Hunyuan3DDiTFlowMatchingPipeline
from pydantic import BaseModel
from fastapi.responses import FileResponse
import runpod

import requests

class GenerateModelRequest(BaseModel):
    image_url: str
    presigned_url: str

cache_dir = "/workspace/hunyuan3d/cache"

pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained('tencent/Hunyuan3D-2', device='cuda', cache_dir=cache_dir)
   
def random_string(length: int) -> str:
    import secrets
    import string
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))

def handler(event):
    request: GenerateModelRequest = GenerateModelRequest(**event['input'])

    # Send a GET request to the image URL
    response = requests.get(request.image_url)

    # Check if the request was successful
    if response.status_code == 200:
        # Open a file in binary write mode to save the image
        with open("downloaded_image.png", "wb") as file:
            file.write(response.content)  # Write the content of the image
        print("Image downloaded successfully.")
    else:
        return {
            "message":"cannot download image",
            "status_code":404
        }

    mesh = pipeline(image="downloaded_image.png")[0]
    mesh_file_loc = f"mesh{random_string(16)}.glb"
    mesh.export(mesh_file_loc)

    try:
        with open(mesh_file_loc, "rb") as f:
            resp = requests.put(
                request.presigned_url,
                data=f,
                headers={"Content-Type": "model/gltf-binary"}
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

    #TODO: how to send the file to the server (maybe S3 or directly streaming)
    return {
        "message":f"success. File uploaded to {request.presigned_url}",
        "status_code":200
    }

if __name__ == '__main__':
    runpod.serverless.start({'handler': handler })