from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from hy3dgen.shapegen.pipelines import Hunyuan3DDiTFlowMatchingPipeline
from pydantic import BaseModel
from fastapi.responses import FileResponse

from PIL import Image
from io import BytesIO

import requests

class GenerateModelRequest(BaseModel):
    image_url: str

# Global variable to hold the model
pipeline = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline
    # Load the ML model
    pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained('tencent/Hunyuan3D-2', device='cuda')
    yield
    # Clean up the ML models and release the resources

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

def random_string(length: int) -> str:
    import secrets
    import string
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))

@app.post("/model/generate")
async def api_generate_model(request: GenerateModelRequest):

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
            "message":"cannot download image"
        }

    mesh = pipeline(image="downloaded_image.png")[0]
    mesh_file_loc = f"static/mesh{random_string(16)}.glb"
    mesh.export(mesh_file_loc)
    #TODO: how to send the file to the server (maybe S3 or directly streaming)
    return FileResponse(
        path=mesh_file_loc,
        media_type="model/gltf-binary",
        filename="result.glb"
    )
    return {
        "model_loc":mesh_file_loc
    }
