import json
import os
import urllib.request
from pathlib import Path

import boto3

MODEL = "phi3.5:latest"

OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://host.k3d.internal:11434/api/generate",
)

S3_ENDPOINT = os.getenv(
    "S3_ENDPOINT",
    "http://seaweedfs-s3.data.svc.cluster.local:8333",
)

BUCKET = "datasets"
DATASET_KEY = "commands_pool.jsonl"

PROMPT_PATH = Path("prompts/teacher_prompt.txt")
DATASET_PATH = Path("/tmp/commands_pool.jsonl")

SHARD_INDEX = int(os.getenv("SHARD_INDEX", "0"))
SHARD_COUNT = int(os.getenv("SHARD_COUNT", "1"))

s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id="any",
    aws_secret_access_key="any",
    region_name="us-east-1",
)


def download_dataset():
    print("Downloading dataset from SeaweedFS...")

    s3.download_file(
        BUCKET,
        DATASET_KEY,
        str(DATASET_PATH),
    )

    print("Dataset downloaded successfully.")


def load_commands():
    commands = []

    with DATASET_PATH.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file):
            if not line.strip():
                continue

            command = json.loads(line)

            if line_number % SHARD_COUNT == SHARD_INDEX:
                commands.append(command)

    return commands


def load_prompt():
    return PROMPT_PATH.read_text(encoding="utf-8")


def call_teacher(command_text, prompt_template):
    prompt = prompt_template.replace(
        "{command}", command_text
    )

    request_data = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
            "seed": 42,
        },
    }

    request_body = json.dumps(request_data).encode("utf-8")

    request = urllib.request.Request(
        OLLAMA_URL,
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=300) as response:
        response_data = json.loads(
            response.read().decode("utf-8")
        )

    return response_data["response"]


def main():
    if SHARD_COUNT < 1:
        raise ValueError("SHARD_COUNT must be at least 1")

    if not 0 <= SHARD_INDEX < SHARD_COUNT:
        raise ValueError(
            "SHARD_INDEX must be between 0 and SHARD_COUNT - 1"
        )

    download_dataset()

    commands = load_commands()

    TEST_LIMIT = int(os.getenv("TEST_LIMIT", "0"))

    if TEST_LIMIT > 0:
        commands = commands[:TEST_LIMIT]

    prompt_template = load_prompt()

    output_path = Path(f"/tmp/shard-{SHARD_INDEX}.jsonl")

    print(f"Worker shard: {SHARD_INDEX}")
    print(f"Total shards: {SHARD_COUNT}")
    print(f"Commands assigned: {len(commands)}")

    with output_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as output_file:

        for index, command in enumerate(commands, start=1):
            command_id = command["id"]
            command_text = command["text"]

            print(
                f"[{index}/{len(commands)}] "
                f"Processing {command_id}"
            )

            teacher_raw = call_teacher(
                command_text,
                prompt_template,
            )

            record = {
                "id": command_id,
                "text": command_text,
                "teacher_raw": teacher_raw,
            }

            output_file.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )

            output_file.flush()

    output_key = f"teacher/shard-{SHARD_INDEX}.jsonl"

    print(f"Uploading output to s3://{BUCKET}/{output_key}")

    s3.upload_file(
        str(output_path),
        BUCKET,
        output_key,
    )

    print(f"Shard completed: {output_key}")


if __name__ == "__main__":
    main()