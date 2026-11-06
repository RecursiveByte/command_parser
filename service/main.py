import json
import os
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import boto3
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from jsonschema import ValidationError, validate
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_URI = os.getenv("MODEL_URI", "s3://models/models/v1")
MODEL_VERSION = os.getenv("MODEL_VERSION", "v1")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:8333")
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "60"))
FAULT_INJECT = os.getenv("FAULT_INJECT", "0")
POD_NAME = os.getenv("HOSTNAME", "unknown")

MODEL_DIR = Path("/tmp/command-parser-model")
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.json"
KEYS = {"intent", "date", "time", "place"}

model = None
tokenizer = None
ready = False
schema = None


class ParseRequest(BaseModel):
    text: str


def download_model():
    """Download model files from object storage (SeaweedFS S3)."""
    bucket, prefix = MODEL_URI.replace("s3://", "").split("/", 1)
    prefix = prefix.rstrip("/")

    s3 = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    paginator = s3.get_paginator("list_objects_v2")
    count = 0

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix + "/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            relative = key[len(prefix) + 1:]
            if not relative or relative.endswith("/"):
                continue
            local = MODEL_DIR / relative
            local.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, key, str(local))
            count += 1

    if count == 0:
        raise RuntimeError(f"No model files found at {MODEL_URI}")
    print(f"Downloaded {count} files from {MODEL_URI}", flush=True)


def load_all():
    """Runs in a background thread so /healthz and /readyz respond while loading."""
    global model, tokenizer, ready
    try:
        download_model()
        tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
        model = AutoModelForCausalLM.from_pretrained(str(MODEL_DIR))
        model.eval()
        ready = True
        print("Model loaded successfully.", flush=True)
    except Exception as e:
        print(f"Model load failed: {e}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global schema
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)["json_schema"]
    threading.Thread(target=load_all, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    if not ready:
        raise HTTPException(status_code=503, detail="model_not_ready")
    return {"status": "ready"}


def extract_json(text):
    match = re.search(r"\{[^{}]*\}", text)
    if not match:
        raise ValueError("No JSON object found")
    return json.loads(match.group(0))


def generate_output(text):
    # Must match the training format exactly
    prompt = f"Command: {text}\nJSON:"
    inputs = tokenizer(prompt, return_tensors="pt")

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )

    new_tokens = outputs[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True)


def headers():
    return {"X-Model-Version": MODEL_VERSION, "X-Served-By": POD_NAME}


@app.post("/parse")
def parse_command(request: ParseRequest):
    if not ready:
        raise HTTPException(status_code=503, detail="model_not_ready")

    output_text = "not json" if FAULT_INJECT == "1" else generate_output(request.text)

    try:
        parsed = extract_json(output_text)
        validate(instance=parsed, schema=schema)
        if set(parsed.keys()) != KEYS:
            raise ValidationError("Unexpected keys")
    except (ValueError, json.JSONDecodeError, ValidationError):
        return JSONResponse(
            status_code=500,
            content={"error": "invalid_model_output"},
            headers=headers(),
        )

    return JSONResponse(status_code=200, content=parsed, headers=headers())