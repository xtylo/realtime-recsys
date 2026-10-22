"""The single place that decides whether S3 is the real service or the local emulator (moto)."""

import os

import boto3
from botocore.config import Config


def s3_client():
    """boto3 S3 client. S3_ENDPOINT_URL empty or unset = real AWS; a URL = local S3 (moto)."""
    endpoint = os.getenv("S3_ENDPOINT_URL") or None
    config = Config(s3={"addressing_style": "path"}) if endpoint else None
    return boto3.client("s3", endpoint_url=endpoint, config=config)
