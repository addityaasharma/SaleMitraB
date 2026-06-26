"""
Run this on your server (where the env vars are set) to isolate the R2 auth issue.
    python r2_diagnose.py
"""

import os
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

s3 = boto3.client(
    "s3",
    endpoint_url=os.getenv("R2_ENDPOINT"),
    aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
    region_name="auto",
    config=Config(signature_version="s3v4"),
)

bucket = os.getenv("R2_BUCKET_NAME")
print(f"Endpoint:    {os.getenv('R2_ENDPOINT')}")
print(f"Bucket:      {bucket}")
print(
    f"Access key:  {os.getenv('R2_ACCESS_KEY_ID')[:6]}... (showing first 6 chars only)"
)
print("-" * 50)

# Test 1: can we list buckets at all? (validates credentials are recognized)
print("\n[1] Testing credentials (list_buckets)...")
try:
    resp = s3.list_buckets()
    names = [b["Name"] for b in resp.get("Buckets", [])]
    print(f"    OK. Buckets visible to this token: {names}")
    if bucket not in names:
        print(
            f"    !! WARNING: '{bucket}' is NOT in the list of buckets "
            f"this token can see. Check R2_BUCKET_NAME or the token's bucket scope."
        )
except ClientError as e:
    print(f"    FAILED: {e.response['Error']}")
    print(
        "    -> Credentials themselves are likely invalid/expired, or this token "
        "has no list permission (some R2 tokens scope out ListBuckets - try test 2 too)."
    )

# Test 2: can we read from the specific bucket? (validates bucket-level read access)
print(f"\n[2] Testing read access on bucket '{bucket}' (list_objects_v2)...")
try:
    s3.list_objects_v2(Bucket=bucket, MaxKeys=1)
    print("    OK. Token has at least read access to this bucket.")
except ClientError as e:
    print(f"    FAILED: {e.response['Error']}")

# Test 3: can we write to the bucket? (the actual operation that's failing)
print(f"\n[3] Testing write access on bucket '{bucket}' (put_object)...")
try:
    s3.put_object(
        Bucket=bucket,
        Key="diagnostics/r2_test.txt",
        Body=b"test",
        ContentType="text/plain",
    )
    print("    OK. Write succeeded - the token DOES have write access.")
    print(
        "    -> If your app still fails, the issue is elsewhere (e.g. ContentType, file object, env var not loaded in that process)."
    )
    s3.delete_object(Bucket=bucket, Key="diagnostics/r2_test.txt")
except ClientError as e:
    print(f"    FAILED: {e.response['Error']}")
    print(
        "    -> This confirms: the token does not have WRITE permission on this bucket."
    )
    print(
        "    -> Fix: go to Cloudflare dashboard > R2 > Manage API tokens, and either:"
    )
    print(
        "       a) create a new token with 'Object Read & Write' permission scoped to this bucket, or"
    )
    print("       b) edit the existing token's permissions if the dashboard allows it.")
