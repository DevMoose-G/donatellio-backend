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
            ClientMethod=client_method, Params=method_parameters, ExpiresIn=expires_in
        )
    except ClientError:
        print(f"Couldn't get a presigned URL for client method '{client_method}'.")
        raise
    return url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bucket", help="The name of the bucket.")
    parser.add_argument(
        "key",
        help="The key (path and filename) in the S3 bucket.",
    )
    parser.add_argument(
        "type",
        help="File type ('png' or 'glb')",
    )
    parser.add_argument(
        "client_method",
        help="The name of the client method that the URL performs.",
        default="put_object",
    )
    args = parser.parse_args()

    # By default, this will use credentials from ~/.aws/credentials
    s3_client = boto3.client("s3", region_name="us-east-1")

    # The presigned URL is specified to expire in 3600  seconds (an hour)
    content_mapping = {
        "png": "image/png",
        "glb": "model/gltf-binary",
        "pt": "application/octet-stream"
    }
    content_type = content_mapping.get(args.type, None)
    if content_type is None:
        raise ValueError(f"Unsupported file type: {args.type}. Supported types are: {', '.join(content_mapping.keys())}")
    urls = []
    if content_type == "image/png":
        if args.client_method == "put_object":
            for i in range(6):
                method_params = {
                    "Bucket": args.bucket,
                    "Key": args.key + "_" + str(i) + ".png",
                    "ContentType": "image/png",
                }

                urls.append(
                    generate_presigned_url(
                        s3_client,
                        str(args.client_method),
                        method_params,  # , "ContentType": "model/gltf-binary"
                        3600,
                    )
                )
        else:
            method_params = {"Bucket": args.bucket, "Key": args.key + ".png"}
            urls.append(
                generate_presigned_url(
                    s3_client,
                    str(args.client_method),
                    method_params,  # , "ContentType": "model/gltf-binary"
                    36000,
                )
            )
    elif content_type == "model/gltf-binary":
        method_params = {
            "Bucket": args.bucket,
            "Key": args.key + ".glb",
            "ContentType": "model/gltf-binary",
        }
        if args.client_method != "put_object":
            del method_params["ContentType"]
        urls.append(
            generate_presigned_url(
                s3_client,
                str(args.client_method),
                method_params,
                3600,
            )
        )
    elif content_type == "application/octet-stream":
        method_params = {
            "Bucket": args.bucket,
            "Key": args.key + ".pt",
            "ContentType": "application/octet-stream",
        }
        if args.client_method != "put_object":
            del method_params["ContentType"]
        urls.append(
            generate_presigned_url(
                s3_client,
                str(args.client_method),
                method_params,
                3600,
            )
        )
    print(f"Generated {args.client_method} presigned URL: {urls}")


if __name__ == "__main__":
    main()
