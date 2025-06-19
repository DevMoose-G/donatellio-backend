import os
from typing import Dict, Optional, Union

import requests
import runpod
from pydantic import BaseModel
from step1x3d_geometry.models.pipelines.pipeline import Step1X3DGeometryPipeline
from torch import set_float32_matmul_precision

set_float32_matmul_precision("high")


class GenerateModelRequest(BaseModel):
    image_url: str
    mesh_presigned_urls_mapping: Dict[str, str]
    n_meshes: int = 1

    seed: int = None

    # use these two for finer detail & smoother meshes
    n_inference_steps: int = 50
    octree_resolution: int = 256  # 256, 384, 512, 768, 1024

    guidance_scale: float = 7.5
    max_facenum: int = 200_000

    # if you see gaps or thin bits dropped, rerun with mc_level slightly negative (e.g. -0.05).
    # if your silhouette is too bloated or fuzzy, push mc_level slightly positive (e.g. +0.02).
    # don’t exceed ±0.1 in either direction on a 2×2×2 volume
    mc_level: float = 0.0

    do_shade_smooth: bool = True

    # needs testing
    label: Union[str | dict] = None
    caption: Optional[str] = None


on_runpod = os.getenv("ON_RUNPOD", False)
cache_dir = "/runpod-volume/cache/step1x-3d"

MODEL_ID = "stepfun-ai/Step1X-3D"
device = "cuda"

if on_runpod:
    if not os.path.isdir(cache_dir):
        raise Exception(f"Cannot find cached model at {cache_dir}")

geom_pipe = Step1X3DGeometryPipeline.from_pretrained(
    cache_dir if on_runpod else "stepfun-ai/Step1X-3D",
    subfolder="Step1X-3D-Geometry-1300m",
).to(device)


def generate_meshes(request: GenerateModelRequest, n_meshes: int) -> str:
    out = geom_pipe(
        request.image_url,
        label=request.label,
        generator=request.seed,
        caption=request.caption,
        num_meshes_per_prompt=n_meshes,
        octree_resolution=request.octree_resolution,
        guidance_scale=request.guidance_scale,
        num_inference_steps=request.n_inference_steps,
        max_facenum=request.max_facenum,
        do_remove_degenerate_face=True,
        do_shade_smooth=request.do_shade_smooth,
        mc_level=request.mc_level,
    )

    # export untextured mesh as .glb format
    # meshes = []
    # untexture_mesh = remove_degenerate_face(out.mesh[0])
    # untexture_mesh = reduce_face(untexture_mesh)
    return out.mesh


def random_string(length: int) -> str:
    import secrets
    import string

    return "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(length)
    )


def upload_asset(file_loc, presigned_url, content_type):
    try:
        with open(file_loc, "rb") as f:
            resp = requests.put(
                presigned_url, data=f, headers={"Content-Type": content_type}
            )

        if resp.status_code != 200:
            return {
                "message": f"cannot upload glb file. Response Code: {resp.status_code}. Response: {resp.text}",
                "status_code": 404,
            }
    except Exception as e:
        return {"message": f"cannot upload glb file. {e}", "status_code": 404}

    return {"status_code": 200}


def generator_handler(event):
    request: GenerateModelRequest = GenerateModelRequest(**event["input"])
    if len(request.mesh_presigned_urls_mapping.keys()) != request.n_meshes:
        yield {"message": "# of presigned urls must match the # of meshes generated"}
        raise Exception("# of presigned urls must match the # of meshes generated")

    # As soon as a mesh is done, yield it
    for mesh_id, presigned_url in request.mesh_presigned_urls_mapping.items():
        mesh = generate_meshes(request, 1)[0]

        # upload
        mesh_file_loc = f"mesh{random_string(16)}.glb"
        mesh.export(mesh_file_loc)
        response = upload_asset(mesh_file_loc, presigned_url, "model/gltf-binary")
        if response["status_code"] != 200:
            yield {"message": "failed to upload mesh", "error_msg": response}
            continue

        yield {
            "message": f"success. Mesh uploaded to {presigned_url}",
            "presigned_url": presigned_url,
            "mesh_id": mesh_id,
            "status_code": 200,
        }


# Start with streaming enabled
if __name__ == "__main__":
    runpod.serverless.start(
        {"handler": generator_handler, "return_aggregate_stream": True}
    )
