import boto3
from botocore.exceptions import ClientError

class StorageProvider:

    def __init__(self):
        self.s3_client = boto3.client("s3")
        self.bucket = "donatellio"

    def __generate_presigned_url(self, client_method, method_parameters, expires_in):
        """
        Generate a presigned Amazon S3 URL that can be used to perform an action.
        
        :param s3_client: A Boto3 Amazon S3 client.
        :param client_method: The name of the client method that the URL performs.
        :param method_parameters: The parameters of the specified client method.
        :param expires_in: The number of seconds the presigned URL is valid for.
        :return: The presigned URL.
        """
        url = self.s3_client.generate_presigned_url(
            ClientMethod=client_method,
            Params=method_parameters,
            ExpiresIn=expires_in
        )
        return url
    
    def generate_presigned_url_for_mesh(self, mesh_name):
        self.__generate_presigned_url(
            "put_object", 
            {"Bucket": self.bucket, "Key": f"meshes/{mesh_name}.glb", "ContentType": "model/gltf-binary"},
            3600 # 1 hr
        )