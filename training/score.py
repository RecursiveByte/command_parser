import argparse
import json
import re
from pathlib import Path

import torch
from jsonschema import ValidationError, validate
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parent.parent
VALIDATION_PATH = ROOT / "data" / "validation.jsonl"
SCHEMA_PATH = ROOT / "service" / "schema.json"

MAX_NEW_TOKENS = 64
MAX_INPUT_LENGTH = 128


def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def extract_json(text):
    match = re.search(r"\{[^{}]*\}", text)

    if not match:
        return None

    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

    if not isinstance(value, dict):
        return None

    return value


def load_model(model_path):
    tokenizer = AutoTokenizer.from_pretrained(model_path)

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.float32,
    )

    model.to("cpu")
    model.eval()

    return tokenizer, model


def predict(command, tokenizer, model):
    prompt = f"Command: {command}\nJSON:"

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=MAX_INPUT_LENGTH,
    )

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    new_tokens = outputs[0][inputs["input_ids"].shape[1]:]

    return tokenizer.decode(
        new_tokens,
        skip_special_tokens=True,
    ).strip()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--model",
        default=str(ROOT / "training" / "output" / "v2"),
        help="Path to the trained model directory",
    )

    parser.add_argument(
        "--validation",
        default=str(VALIDATION_PATH),
        help="Path to validation JSONL file",
    )

    parser.add_argument(
        "--min-validity",
        type=float,
        default=0.0,
        help="Minimum required valid JSON percentage",
    )

    args = parser.parse_args()

    if not 0 <= args.min_validity <= 100:
        raise ValueError("--min-validity must be between 0 and 100")

    records = load_jsonl(args.validation)

    if not records:
        raise ValueError("Validation dataset is empty")

    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)["json_schema"]

    tokenizer, model = load_model(args.model)

    valid_count = 0
    total = len(records)

    for index, record in enumerate(records, start=1):
        command = record["text"]

        raw_output = predict(command, tokenizer, model)
        prediction = extract_json(raw_output)

        is_valid = False

        if prediction is not None:
            try:
                validate(instance=prediction, schema=schema)
                is_valid = True
            except ValidationError:
                is_valid = False

        if is_valid:
            valid_count += 1

        print(
            f"{index}/{total} | "
            f"Valid JSON: {is_valid}"
        )

    validity_rate = (valid_count / total) * 100

    print("\n--- Model Evaluation ---")
    print(f"Total examples: {total}")
    print(f"Valid predictions: {valid_count}")
    print(f"Invalid predictions: {total - valid_count}")
    print(f"Valid JSON Rate: {validity_rate:.2f}%")
    print(f"Required minimum: {args.min_validity:.2f}%")

    if validity_rate < args.min_validity:
        print("QUALITY GATE FAILED")
        raise SystemExit(1)

    print("QUALITY GATE PASSED")


if __name__ == "__main__":
    main()
