
import json
from pathlib import Path

CONFIG_PATH = Path("training/config.yaml")
DATASET_PATH = Path("data/train_v3.jsonl")
OUTPUT_PATH = Path("training/processed_train.jsonl")

import yaml

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

train_samples = config["train_samples"]

with open(DATASET_PATH, "r", encoding="utf-8") as f:
    records = [json.loads(line) for line in f]

records = records[:train_samples]

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    for record in records:
        text = f"Command: {record['text']}\nJSON: {record['teacher_raw']}"

        json.dump({"text": text}, f, ensure_ascii=False)
        f.write("\n")

print(f"Prepared {len(records)} training examples")
print(f"Output: {OUTPUT_PATH}")
