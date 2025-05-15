import argparse
import boto3
from botocore.exceptions import ClientError

def generate_presigned_url(s3_client, client_method, method_parameters, expires_in):
    """
    Generate a presigned Amazon S3 URL that can be used to perform an action.
    
    :param s3_client: A Boto3 Amazon S3 client.
    :param client_method: The name of the client method that the URL performs.
    :param method_parameters: The parameters of the specified client method.
    :param expires_in: The number of seconds the presigned URL is valid for.
    :return: The presigned URL.
    """
    try:
        url = s3_client.generate_presigned_url(
            ClientMethod=client_method,
            Params=method_parameters,
            ExpiresIn=expires_in
        )
    except ClientError:
        print(f"Couldn't get a presigned URL for client method '{client_method}'.")
        raise
    return url

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bucket", help="The name of the bucket.")
    parser.add_argument(
        "key", help="The key (path and filename) in the S3 bucket.",
    )
    parser.add_argument(
        "type", help="File type ('png' or 'glb')",
    )
    args = parser.parse_args()
    
    # By default, this will use credentials from ~/.aws/credentials
    s3_client = boto3.client("s3")
    
    # The presigned URL is specified to expire in 10_000 seconds
    content_type = "image/png" if args.type == "png" else "model/gltf-binary"
    urls = []
    if content_type == "image/png":
        for i in range(6):
            urls.append(generate_presigned_url(
                s3_client, 
                "put_object", 
                {"Bucket": args.bucket, "Key": args.key+"_"+str(i)+".png", "ContentType": "image/png"},  # , "ContentType": "model/gltf-binary"
                10_000
            ))
    else:
        urls.append(generate_presigned_url(
            s3_client, 
            "put_object", 
            {"Bucket": args.bucket, "Key": args.key, "ContentType": "model/gltf-binary"},  # , "ContentType": "model/gltf-binary"
            10_000
        ))
    print(f"Generated PUT presigned URL: {urls}")

if __name__ == "__main__":
    main()