import os
from typing import Dict, List, Optional, Union

import requests
import runpod
from pydantic import BaseModel
from step1x3d_geometry.models.pipelines.pipeline import Step1X3DGeometryPipeline
from torch import FloatTensor, load, save, set_float32_matmul_precision

set_float32_matmul_precision("high")


class BaseRequest(BaseModel):
    start_from_latents: bool
    n_meshes: int = 1


class ModifyMeshRequest(BaseRequest):
    mesh_presigned_urls_mapping: Dict[str, List[str]]

    mc_level: float = 0.0
    octree_resolution: int = 256
    max_facenum: int = 200_000
    do_shade_smooth: bool = True


class GenerateModelRequest(BaseRequest):
    image_url: str
    mesh_presigned_urls_mapping: Dict[str, List[str]]

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
    subfolder="Step1X-3D-Geometry-Label-1300m",
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

    return out.mesh


def generate_latents(request: GenerateModelRequest, n_meshes: int) -> FloatTensor:
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
        output_type="latent",
    )

    return out.mesh


def random_string(length: int) -> str:
    import secrets
    import string

    return "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(length)
    )


def download_file(url: str, file_loc: str):
    try:
        resp = requests.get(url, stream=True)
        if resp.status_code != 200:
            raise Exception(
                f"Failed to download file from {url}. Response Code: {resp.status_code}. Response: {resp.text}"
            )

        with open(file_loc, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
    except Exception as e:
        raise Exception(f"Error downloading file from {url}: {e}")


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
    request: BaseRequest = BaseRequest(**event["input"])
    if request.start_from_latents:
        request: ModifyMeshRequest = ModifyMeshRequest(**event["input"])
        if len(request.mesh_presigned_urls_mapping.keys()) != request.n_meshes:
            yield {
                "message": "# of presigned urls must match the # of meshes generated"
            }
            raise Exception("# of presigned urls must match the # of meshes generated")

        # As soon as a mesh is done, yield it
        i = 0
        for mesh_id, presigned_urls in request.mesh_presigned_urls_mapping.items():
            latents_presigned_url = presigned_urls[0]

            download_file(latents_presigned_url, f"latents_{i}.pt")
            latents = load(f"latents_{i}.pt")

            # save latents to a file and upload file to s3
            save(latents, f"latents_{i}.pt")
            upload_asset(
                f"latents_{i}.pt", latents_presigned_url, "application/octet-stream"
            )

            # turn latents into a mesh
            mesh = geom_pipe.postprocess_mesh(
                latents,
                mc_level=request.mc_level,
                octree_resolution=request.octree_resolution,
                do_remove_degenerate_face=True,
                do_shade_smooth=request.do_shade_smooth,
                max_facenum=request.max_facenum,
            )[0]

            # upload
            mesh_presigned_url = presigned_urls[1]

            mesh_file_loc = f"mesh{random_string(16)}.glb"
            mesh.export(mesh_file_loc)
            n_faces = mesh.faces.shape[0]
            response = upload_asset(
                mesh_file_loc, mesh_presigned_url, "model/gltf-binary"
            )
            if response["status_code"] != 200:
                yield {"message": "failed to upload mesh", "error_msg": response}
                continue

            yield {
                "message": f"success. Mesh uploaded to {mesh_presigned_url}",
                "latents_presigned_url": latents_presigned_url,
                "mesh_presigned_url": mesh_presigned_url,
                "face_count": n_faces,
                "mesh_id": i,
                "status_code": 200,
            }
            i += 1

    else:
        request: GenerateModelRequest = GenerateModelRequest(**event["input"])
        if len(request.mesh_presigned_urls_mapping.keys()) != request.n_meshes:
            yield {
                "message": "# of presigned urls must match the # of meshes generated"
            }
            raise Exception("# of presigned urls must match the # of meshes generated")

        # As soon as a mesh is done, yield it
        for mesh_id, presigned_urls in request.mesh_presigned_urls_mapping.items():
            latents_presigned_url = presigned_urls[0]
            mesh_presigned_url = presigned_urls[1]

            # mesh = generate_meshes(request, 1)[0]
            latents = generate_latents(request, 1)

            # save latents to a file and upload file to s3
            save(latents, f"latents_{mesh_id}.pt")
            upload_asset(
                f"latents_{mesh_id}.pt",
                latents_presigned_url,
                "application/octet-stream",
            )

            # turn latents into a mesh
            mesh = geom_pipe.postprocess_mesh(
                latents,
                mc_level=request.mc_level,
                octree_resolution=request.octree_resolution,
                # do_remove_floater: bool = True,
                # do_reduce_face: bool = True,
                do_remove_degenerate_face=True,
                do_shade_smooth=request.do_shade_smooth,
                max_facenum=request.max_facenum,
            )[0]

            # upload
            mesh_file_loc = f"mesh{random_string(16)}.glb"
            mesh.export(mesh_file_loc)
            n_faces = mesh.faces.shape[0]
            response = upload_asset(
                mesh_file_loc, mesh_presigned_url, "model/gltf-binary"
            )
            if response["status_code"] != 200:
                yield {"message": "failed to upload mesh", "error_msg": response}
                continue

            yield {
                "message": f"success. Mesh uploaded to {mesh_presigned_url}",
                "latents_presigned_url": latents_presigned_url,
                "mesh_presigned_url": mesh_presigned_url,
                "mesh_id": mesh_id,
                "face_count": n_faces,
                "status_code": 200,
            }


# Start with streaming enabled
if __name__ == "__main__":
    runpod.serverless.start(
        {"handler": generator_handler, "return_aggregate_stream": True}
    )
