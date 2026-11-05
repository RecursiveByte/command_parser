
import argparse
import hashlib
import json
from pathlib import Path

ALLOWED_INTENTS = {
    "alarm_set",
    "alarm_query",
    "calendar_set",
    "calendar_query",
    "calendar_remove",
    "weather_query",
    "datetime_query",
    "recommendation_events",
}

EXPECTED_KEYS = {"intent", "date", "time", "place"}


def load_records(shard_paths):
    records = []
    invalid_json_count = 0

    for shard_path in shard_paths:
        with shard_path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                    records.append(record)

                except json.JSONDecodeError:
                    invalid_json_count += 1
                    print(
                        f"Invalid JSON: {shard_path}, "
                        f"line {line_number}"
                    )

    return records, invalid_json_count


def parse_teacher_reply(raw_reply):
    try:
        return json.loads(raw_reply)
    except (json.JSONDecodeError, TypeError):
        return None


def slot_values_are_valid(label, command):
    command_lower = command.lower()

    for slot_name in ("date", "time", "place"):
        value = label[slot_name]

        if value is None:
            continue

        if not isinstance(value, str):
            return False

        if value.lower() not in command_lower:
            return False

    return True

def clean_records(records, invalid_json_count):
    counts = {
        "input_records": len(records) + invalid_json_count,
        "rejected_invalid_json": invalid_json_count,
        "rejected_wrong_keys": 0,
        "rejected_invalid_intent": 0,
        "rejected_invalid_slots": 0,
        "duplicates": 0,
        "kept": 0,
    }

    valid_records = []
    rejected_records = []

    def reject(record, reason):
        rejected_records.append({
            "record": record,
            "rejection_reason": reason
        })

    for record in records:
        if not isinstance(record, dict):
            counts["rejected_wrong_keys"] += 1
            reject(record, "wrong_record_type")
            continue

        raw_reply = record.get("teacher_raw")
        command = record.get("text")

        if not isinstance(raw_reply, str):
            counts["rejected_invalid_json"] += 1
            reject(record, "teacher_raw_not_string")
            continue

        if not isinstance(command, str):
            counts["rejected_invalid_slots"] += 1
            reject(record, "command_not_string")
            continue

        label = parse_teacher_reply(raw_reply)

        if label is None:
            counts["rejected_invalid_json"] += 1
            reject(record, "invalid_teacher_json")
            continue

        if not isinstance(label, dict):
            counts["rejected_wrong_keys"] += 1
            reject(record, "label_not_object")
            continue

        if set(label.keys()) != EXPECTED_KEYS:
            counts["rejected_wrong_keys"] += 1
            reject(record, "wrong_label_keys")
            continue

        if not isinstance(label["intent"], str):
            counts["rejected_invalid_intent"] += 1
            reject(record, "intent_not_string")
            continue

        if label["intent"] not in ALLOWED_INTENTS:
            counts["rejected_invalid_intent"] += 1
            reject(record, "intent_not_allowed")
            continue

        if not slot_values_are_valid(label, command):
            counts["rejected_invalid_slots"] += 1
            reject(record, "slot_not_found_in_command")
            continue

        valid_records.append(record)

    valid_records.sort(key=lambda record: record["id"])

    unique_records = []
    seen_commands = set()

    for record in valid_records:
        command_key = record["text"].strip().lower()

        if command_key in seen_commands:
            counts["duplicates"] += 1
            reject(record, "duplicate_command")
            continue

        seen_commands.add(command_key)
        unique_records.append(record)

    counts["kept"] = len(unique_records)

    return unique_records, counts, rejected_records


def write_dataset(records, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as file:

        for record in records:
            file.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )


def write_checksum(dataset_path, checksum_path):
    sha256 = hashlib.sha256()

    with dataset_path.open("rb") as file:
        for chunk in iter(
            lambda: file.read(1024 * 1024), b""
        ):
            sha256.update(chunk)

    checksum = sha256.hexdigest()

    checksum_path.parent.mkdir(parents=True, exist_ok=True)

    checksum_path.write_text(
        f"{checksum}  {dataset_path.name}\n",
        encoding="utf-8",
    )

    return checksum


def main():
    parser = argparse.ArgumentParser(
        description="Clean teacher-generated JSONL shards"
    )

    parser.add_argument(
        "--shards",
        nargs="+",
        required=True,
        help="Teacher shard JSONL files",
    )

    parser.add_argument(
        "--output",
        default="datasets/v1/train.jsonl",
    )

    parser.add_argument(
        "--checksum",
        default="datasets/v1/train.sha256",
    )

    args = parser.parse_args()

    shard_paths = [Path(path) for path in args.shards]

    records, invalid_json_count = load_records(shard_paths)

    cleaned_records, counts, rejected_records = clean_records(
        records, invalid_json_count
    )

    output_path = Path(args.output)
    checksum_path = Path(args.checksum)
    
    rejected_path = Path("data/rejected.jsonl")
    write_dataset(rejected_records, rejected_path)
    
    write_dataset(cleaned_records, output_path)

    checksum = write_checksum(
        output_path,
        checksum_path,
    )

    print("\nCleaning Summary")

    for name, value in counts.items():
        print(f"{name}: {value}")

    print(f"\nSHA-256: {checksum}")

    total = (
        counts["rejected_invalid_json"]
        + counts["rejected_wrong_keys"]
        + counts["rejected_invalid_intent"]
        + counts["rejected_invalid_slots"]
        + counts["duplicates"]
        + counts["kept"]
    )

    if total != counts["input_records"]:
        raise RuntimeError("Count reconciliation failed!")

    print("\nCount reconciliation passed.")


if __name__ == "__main__":
    main()
