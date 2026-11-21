"""Phase 3, Step 3.7 - copy the Gemini API key from backend\\.env into AWS Parameter Store (encrypted).

Run from the project folder (virtual environment active):
    python infra\\scripts\\push-chat-key.py

The API servers read /cinebook/prod/app/GEMINI_API_KEY when they start. The key is stored as a
SecureString and is never printed. Run this again whenever you change the key locally.
"""
import os
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError

REGION = "ap-south-1"
NAME = "/cinebook/prod/app/GEMINI_API_KEY"
ENV_FILE = os.path.join("backend", ".env")


def main() -> int:
    if not os.path.exists(ENV_FILE):
        print(f"{ENV_FILE} not found - run this from the project folder.")
        return 1
    key = ""
    with open(ENV_FILE, encoding="utf-8-sig") as handle:
        for line in handle:
            if line.startswith("GEMINI_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        print("GEMINI_API_KEY is not set in backend\\.env - run infra\\scripts\\check-gemini.py first.")
        return 1
    try:
        version = boto3.client("ssm", region_name=REGION).put_parameter(
            Name=NAME, Value=key, Type="SecureString", Overwrite=True,
            Description="Gemini API key for the CineBook chat assistant")["Version"]
    except (ClientError, BotoCoreError) as error:
        print(f"Could not save the key: {error}")
        return 1
    print(f"Saved {NAME} (SecureString, version {version}). The key itself was not printed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
