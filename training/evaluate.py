
import argparse
import json
import re
from pathlib import Path

import requests
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM


VALIDATION_PATH = Path("data/validation.jsonl")
STUDENT_PATH = Path("training/output/v1")
BASELINE_MODEL = "EleutherAI/pythia-70m"
TEACHER_MODEL = "phi3.5"
TEACHER_PROMPT_PATH = Path("prompts/teacher_prompt.txt")
RESULTS_DIR = Path("results/v1")

OLLAMA_URL = "http://localhost:11434/api/generate"
DEVICE = torch.device("cpu")
MAX_NEW_TOKENS = 64
SLOTS = ["intent", "date", "time", "place"]


def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def get_command(record):
    for key in ["command", "utterance", "input", "text"]:
        if key in record and isinstance(record[key], str):
            value = record[key]

            if value.startswith("Command: "):
                value = value.split("Command: ", 1)[1]
                value = value.split("\nJSON:", 1)[0]

            return value.strip()

    raise ValueError(f"Command not found in record: {record}")


def get_expected(record):
    for key in ["teacher_response", "teacher", "response", "label", "target", "output", "json"]:
        if key in record:
            value = record[key]

            if isinstance(value, dict):
                return value

            if isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    match = re.search(r"\{.*\}", value, re.DOTALL)

                    if match:
                        return json.loads(match.group(0))

    if all(key in record for key in SLOTS):
        return {key: record[key] for key in SLOTS}

    raise ValueError(f"Expected JSON not found in record: {record}")


def extract_json(text):
    match = re.search(r"\{.*?\}", text, re.DOTALL)

    if not match:
        return None

    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

    if not isinstance(value, dict):
        return None

    if set(value.keys()) != set(SLOTS):
        return None

    return value


def normalize_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def load_model(model_path):
    tokenizer = AutoTokenizer.from_pretrained(model_path)

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.float32
    )

    model.to(DEVICE)
    model.eval()

    return tokenizer, model


def predict_student(command, tokenizer, model):
    prompt = f"Command: {command}\nJSON:"

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=128
    ).to(DEVICE)

    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id
        )

    generated_tokens = output[0][inputs["input_ids"].shape[1]:]

    generated_text = tokenizer.decode(
        generated_tokens,
        skip_special_tokens=True
    )

    return generated_text.strip(), extract_json(generated_text)


def predict_teacher(command, teacher_prompt):
    prompt = teacher_prompt.replace("{command}", command)

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": TEACHER_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0,
                "seed": 42,
                "num_predict": MAX_NEW_TOKENS
            }
        },
        timeout=300
    )

    response.raise_for_status()

    generated_text = response.json()["response"].strip()

    return generated_text, extract_json(generated_text)


def evaluate(name, model_path, records, limit=None, teacher_prompt=None):
    tokenizer = None
    model = None

    if name != "teacher":
        tokenizer, model = load_model(model_path)

    if limit:
        records = records[:limit]

    output_path = RESULTS_DIR / f"{name}_predictions.jsonl"

    total = len(records)
    exact_correct = 0
    valid_json = 0
    slot_correct = {slot: 0 for slot in SLOTS}

    with open(output_path, "w", encoding="utf-8") as f:
        for index, record in enumerate(records, start=1):
            command = get_command(record)
            expected = get_expected(record)

            if name == "teacher":
                raw_prediction, prediction = predict_teacher(
                    command,
                    teacher_prompt
                )
            else:
                raw_prediction, prediction = predict_student(
                    command,
                    tokenizer,
                    model
                )

            exact_match = (
                prediction is not None
                and normalize_json(prediction) == normalize_json(expected)
            )

            if prediction is not None:
                valid_json += 1

            if exact_match:
                exact_correct += 1

            for slot in SLOTS:
                if prediction is not None and prediction.get(slot) == expected.get(slot):
                    slot_correct[slot] += 1

            result = {
                "id": record.get("id", f"V{index:03d}"),
                "command": command,
                "expected": expected,
                "raw_prediction": raw_prediction,
                "prediction": prediction,
                "exact_match": exact_match
            }

            f.write(json.dumps(result, ensure_ascii=False) + "\n")

            print(
                f"{name}: {index}/{total} "
                f"Exact Match: {exact_match}"
            )

    def rate(value):
        return value / total if total else 0.0

    report = {
        "model": name,
        "total_examples": total,
        "correct_predictions": exact_correct,
        "incorrect_predictions": total - exact_correct,
        "exact_match_accuracy": rate(exact_correct),
        "valid_json_rate": rate(valid_json),
        "intent_accuracy": rate(slot_correct["intent"]),
        "date_accuracy": rate(slot_correct["date"]),
        "time_accuracy": rate(slot_correct["time"]),
        "place_accuracy": rate(slot_correct["place"])
    }

    report_path = RESULTS_DIR / f"{name}_validation.json"

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n{name} Evaluation")
    print(f"Exact Match: {exact_correct}/{total} ({report['exact_match_accuracy']:.4f})")
    print(f"Valid JSON Rate: {report['valid_json_rate']:.4f}")
    print(f"Intent Accuracy: {report['intent_accuracy']:.4f}")
    print(f"Date Accuracy: {report['date_accuracy']:.4f}")
    print(f"Time Accuracy: {report['time_accuracy']:.4f}")
    print(f"Place Accuracy: {report['place_accuracy']:.4f}")
    print(f"Report saved to: {report_path}")
    print(f"Predictions saved to: {output_path}")

    if model is not None:
        del model
        del tokenizer

    return report


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip-baseline", action="store_true")
    parser.add_argument("--skip-teacher", action="store_true")

    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    records = load_jsonl(VALIDATION_PATH)

    print(f"Validation examples: {len(records)}")

    comparison = {}

    if not args.skip_teacher:
        with open(TEACHER_PROMPT_PATH, "r", encoding="utf-8") as f:
            teacher_prompt = f.read().strip()

        comparison["teacher"] = evaluate(
            "teacher",
            TEACHER_MODEL,
            records,
            args.limit,
            teacher_prompt
        )

    if not args.skip_baseline:
        comparison["baseline_pythia"] = evaluate(
            "baseline_pythia",
            BASELINE_MODEL,
            records,
            args.limit
        )

    comparison["student_v1"] = evaluate(
        "student_v1",
        STUDENT_PATH,
        records,
        args.limit
    )

    with open(
        RESULTS_DIR / "model_comparison.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(comparison, f, indent=2)

    print("\nEvaluation completed.")


if __name__ == "__main__":
    main()
