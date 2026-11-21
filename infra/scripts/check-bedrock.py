"""Phase 3, Step 3.1 - find a Bedrock model this account can use for the CineBook Assistant.

Run from the project folder (with the virtual environment active):
    python infra\\scripts\\check-bedrock.py

What it does (read-only except for one tiny test question per model tried):
  1. Lists the text models and inference profiles Amazon Bedrock offers in the region.
  2. Tries a short list of small, fast models in order of preference, asking each to reply "OK".
  3. Writes the first one that answers into backend\\.env as CHAT_MODEL_ID.
Nothing is created in AWS. A few test questions cost a fraction of a rupee.
"""
import os
import sys

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

REGION = os.getenv("BEDROCK_REGION", "ap-south-1")
ENV_FILE = os.path.join("backend", ".env")

# Small, fast, low-cost models - best fit first. Matching is by part of the model name.
FORM_HELP = ("Anthropic (Claude) models need a one-time 'use case details' form: AWS console -> Amazon Bedrock ->\n"
             "Model catalog -> open a Claude model -> submit the form, then run this script again.")
PREFERENCES = ["claude-haiku-4-5", "claude-3-5-haiku", "nova-2-lite", "nova-lite", "nova-micro", "claude-3-haiku"]


def discover(bedrock) -> list[tuple[str, str]]:
    """Return (id, description) for every inference profile and on-demand text model in the region."""
    found = []
    token = None
    while True:                                   # inference profiles (how the newest models are offered)
        kwargs = {"maxResults": 100, "typeEquals": "SYSTEM_DEFINED"}
        if token:
            kwargs["nextToken"] = token
        page = bedrock.list_inference_profiles(**kwargs)
        for profile in page.get("inferenceProfileSummaries", []):
            if profile.get("status", "ACTIVE") == "ACTIVE":
                found.append((profile["inferenceProfileId"], "inference profile: " + profile.get("inferenceProfileName", "")))
        token = page.get("nextToken")
        if not token:
            break
    models = bedrock.list_foundation_models(byOutputModality="TEXT", byInferenceType="ON_DEMAND")
    for model in models.get("modelSummaries", []):
        if model.get("modelLifecycle", {}).get("status", "ACTIVE") == "ACTIVE":
            found.append((model["modelId"], "model: " + model.get("modelName", "")))
    return found


def candidates(found: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Order the discovered ids by PREFERENCES; in-country/regional profiles before global ones."""
    ordered, seen = [], set()
    for wanted in PREFERENCES:
        matches = [item for item in found if wanted in item[0]]
        matches.sort(key=lambda item: (item[0].startswith("global."), not item[1].startswith("inference profile"), item[0]))
        for item in matches:
            if item[0] not in seen:
                seen.add(item[0])
                ordered.append(item)
    return ordered


def try_model(runtime, model_id: str) -> tuple[bool, str]:
    try:
        response = runtime.converse(
            modelId=model_id,
            system=[{"text": "You are a connection test. Reply with exactly: OK"}],
            messages=[{"role": "user", "content": [{"text": "Are you there?"}]}],
            inferenceConfig={"maxTokens": 10, "temperature": 0},
        )
        text = "".join(part.get("text", "") for part in response["output"]["message"]["content"]).strip()
        usage = response.get("usage", {})
        return True, f"answered {text!r} ({usage.get('inputTokens', '?')} tokens in, {usage.get('outputTokens', '?')} out)"
    except ClientError as error:
        info = error.response.get("Error", {})
        return False, f"{info.get('Code', 'Error')}: {info.get('Message', '')}"[:300]
    except BotoCoreError as error:
        return False, f"{error.__class__.__name__}: {error}"[:300]


def save_model_id(model_id: str) -> bool:
    if not os.path.exists(ENV_FILE):
        return False
    with open(ENV_FILE, "r", encoding="utf-8-sig", newline="") as handle:
        raw = handle.read()
    newline = "\r\n" if "\r\n" in raw else "\n"
    lines = [line for line in raw.replace("\r\n", "\n").split("\n") if not line.startswith("CHAT_MODEL_ID=")]
    while lines and not lines[-1].strip():
        lines.pop()
    lines.append(f"CHAT_MODEL_ID={model_id}")
    with open(ENV_FILE, "w", encoding="utf-8", newline="") as handle:
        handle.write(newline.join(lines) + newline)
    return True


def main() -> int:
    print(f"Checking Amazon Bedrock in {REGION} ...")
    config = Config(connect_timeout=5, read_timeout=30, retries={"max_attempts": 2})
    try:
        found = discover(boto3.client("bedrock", region_name=REGION, config=config))
    except (ClientError, BotoCoreError) as error:
        print(f"Could not list Bedrock models: {error}")
        return 1
    options = candidates(found)
    print(f"Found {len(found)} text models/profiles; {len(options)} are small models suited to the assistant.")
    if not options:
        print("No suitable model is offered in this region. Paste this output to your guide/trainer.")
        return 1

    runtime = boto3.client("bedrock-runtime", region_name=REGION, config=config)
    needs_form = False
    for model_id, description in options:
        ok, detail = try_model(runtime, model_id)
        print(f"  {'OK    ' if ok else 'FAILED'}  {model_id}")
        print(f"          {description}")
        print(f"          {detail}")
        if ok:
            saved = save_model_id(model_id)
            print()
            print(f"Chosen model: {model_id}")
            print(f"Saved as CHAT_MODEL_ID in {ENV_FILE}" if saved else f"Add this line to {ENV_FILE}:  CHAT_MODEL_ID={model_id}")
            if needs_form:
                print()
                print("Note: a Claude model was preferred but is not enabled on this account yet.")
                print(FORM_HELP)
                print("This is optional - the model chosen above works for the assistant.")
            return 0
        if "anthropic" in model_id and ("use case" in detail.lower() or "AccessDenied" in detail):
            needs_form = True

    print()
    print("No model answered. Nothing was changed.")
    if needs_form:
        print(FORM_HELP)
    return 1


if __name__ == "__main__":
    sys.exit(main())
