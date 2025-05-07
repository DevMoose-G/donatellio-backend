from hy3dgen.shapegen.pipelines import Hunyuan3DDiTFlowMatchingPipeline

from PIL import Image
from io import BytesIO

import requests

pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained('tencent/Hunyuan3D-2', device='cuda')

def random_string(length: int) -> str:
    import secrets
    import string
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))

mesh = pipeline(image="downloaded_image.png")[0]
mesh_file_loc = f"static/mesh{random_string(16)}.glb"
mesh.export(mesh_file_loc)