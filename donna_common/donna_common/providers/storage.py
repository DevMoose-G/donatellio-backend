from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError


def extract_s3_key(presigned_url):
    parsed_url = urlparse(presigned_url)
    # Remove leading '/' from the path to get the object key
    object_key = parsed_url.path.lstrip("/")
    return object_key


class StorageProvider:
    def __init__(self):
        self.s3_client = boto3.client("s3", region_name="us-east-1")
        self.bucket = "donatellio"

    def __generate_presigned_url(
        self, client_method, method_parameters, expires_in
    ) -> str:
        """
        Generate a presigned Amazon S3 URL that can be used to perform an action.

        :param s3_client: A Boto3 Amazon S3 client.
        :param client_method: The name of the client method that the URL performs.
        :param method_parameters: The parameters of the specified client method.
        :param expires_in: The number of seconds the presigned URL is valid for.
        :return: The presigned URL.
        """
        url = self.s3_client.generate_presigned_url(
            ClientMethod=client_method, Params=method_parameters, ExpiresIn=expires_in
        )
        return url

    def generate_put_url_for_mesh(self, mesh_name) -> str:
        return self.__generate_presigned_url(
            "put_object",
            {
                "Bucket": self.bucket,
                "Key": f"meshes/{mesh_name}.glb",
                "ContentType": "model/gltf-binary",
            },
            3600,  # 1 hr
        )

    def generate_put_url_for_latents(self, mesh_name) -> str:
        return self.__generate_presigned_url(
            "put_object",
            {
                "Bucket": self.bucket,
                "Key": f"latents/{mesh_name}.pt",
                "ContentType": "application/octet-stream",
            },
            3600,  # 1 hr
        )

    def generate_put_url_for_image(self, image_name, content_type="image/png") -> str:
        return self.__generate_presigned_url(
            "put_object",
            {
                "Bucket": self.bucket,
                "Key": f"images/{image_name}.png",
                "ContentType": content_type,
            },
            3600,  # 1 hr
        )

    def generate_get_url(self, storage_key: str) -> str:
        return self.__generate_presigned_url(
            "get_object",
            {"Bucket": self.bucket, "Key": storage_key},
            10 * 60,  # 10 mins
        )

    def upload_image(self, image_filename, image_path):
        try:
            key = f"images/{image_filename}"
            self.s3_client.upload_file(image_path, self.bucket, key)
            return key
        except ClientError as e:
            print(e)

    def upload_mesh(self, mesh_id, mesh_filename, mesh_path):
        try:
            key = f"meshes/{mesh_id}/{mesh_filename}"
            self.s3_client.upload_file(mesh_path, self.bucket, key)
            return key
        except ClientError as e:
            print(e)

    def download_file(self, storage_key, local_path):
        try:
            self.s3_client.download_file(self.bucket, storage_key, local_path)
        except ClientError as e:
            print(e)
            raise e
