import csv
import json
import os
import random
from pathlib import Path

import numpy as np
import torch
import yaml
from torch.utils.data import Dataset, DataLoader
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    get_linear_schedule_with_warmup,
)

with open("training/config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

seed = config["seed"]

random.seed(seed)
np.random.seed(seed)
torch.manual_seed(seed)

torch.set_num_threads(4)

device = torch.device(config["device"])

model_name = config["model_name"]
dataset_path = Path("training/processed_train.jsonl")
output_dir = Path(config["output_dir"])
loss_csv = Path(config["loss_csv"])

subset = os.getenv("SUBSET")

if subset:
    subset = int(subset)

output_dir.mkdir(parents=True, exist_ok=True)
loss_csv.parent.mkdir(parents=True, exist_ok=True)

with open(dataset_path, "r", encoding="utf-8") as f:
    records = [json.loads(line) for line in f if line.strip()]

records = records[:config["train_samples"]]

if subset:
    records = records[:subset]

print(f"Training examples: {len(records)}")
print(f"Device: {device}")

tokenizer = AutoTokenizer.from_pretrained(model_name)

if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

tokenizer.padding_side = "right"

model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype=torch.float32,
)
model.to(device)

print("Model dtype:", next(model.parameters()).dtype)

model.config.use_cache = False

SEPARATOR = "\nJSON:"

class CommandDataset(Dataset):
    def __init__(self, records):
        self.records = records

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):
        return self.records[index]["text"]

def collate_fn(texts):
    max_len = config["max_seq_length"]

    ids_list = []
    labels_list = []

    for text in texts:
        prompt, completion = text.split(SEPARATOR, 1)
        prompt = prompt + SEPARATOR

        prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
        completion_ids = tokenizer(completion, add_special_tokens=False)["input_ids"]

        completion_ids = completion_ids + [tokenizer.eos_token_id]

        ids = (prompt_ids + completion_ids)[:max_len]
        labels = ([-100] * len(prompt_ids) + completion_ids)[:max_len]

        ids_list.append(ids)
        labels_list.append(labels)

    longest = max(len(x) for x in ids_list)

    input_ids = []
    attention_mask = []
    labels = []

    for ids, lab in zip(ids_list, labels_list):
        pad = longest - len(ids)
        input_ids.append(ids + [tokenizer.pad_token_id] * pad)
        attention_mask.append([1] * len(ids) + [0] * pad)
        labels.append(lab + [-100] * pad)

    return {
        "input_ids": torch.tensor(input_ids),
        "attention_mask": torch.tensor(attention_mask),
        "labels": torch.tensor(labels),
    }

dataset = CommandDataset(records)

dataloader = DataLoader(
    dataset,
    batch_size=config["batch_size"],
    shuffle=True,
    collate_fn=collate_fn,
    num_workers=0
)

sample = collate_fn([dataset[0]])
print("\n--- Sanity check ---")
print("Full text      :", tokenizer.decode(sample["input_ids"][0]))
trained_ids = sample["labels"][0][sample["labels"][0] != -100]
print("Trained on only:", tokenizer.decode(trained_ids))
print("--------------------\n")

optimizer = torch.optim.AdamW(
    model.parameters(),
    lr=config["learning_rate"],
    weight_decay=0.01
)

total_steps = len(dataloader) * config["epochs"]
scheduler = get_linear_schedule_with_warmup(
    optimizer,
    num_warmup_steps=max(1, int(0.05 * total_steps)),
    num_training_steps=total_steps,
)

with open(loss_csv, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["epoch", "loss"])

    for epoch in range(config["epochs"]):
        model.train()

        total_loss = 0.0
        batch_count = 0

        for batch_index, batch in enumerate(dataloader):
            batch = {
                key: value.to(device)
                for key, value in batch.items()
            }

            if (batch["labels"] != -100).sum().item() == 0:
                print(
                    f"Skipping epoch {epoch + 1}, batch {batch_index + 1}: "
                    f"no supervised tokens (increase max_seq_length)"
                )
                scheduler.step()
                continue

            optimizer.zero_grad(set_to_none=True)

            outputs = model(**batch)

            loss = outputs.loss

            if not torch.isfinite(loss):
                print(f"Invalid loss at epoch {epoch + 1}, batch {batch_index + 1}")
                print("Decoded:", tokenizer.batch_decode(batch["input_ids"]))
                raise ValueError("Training loss is NaN or Inf")

            loss.backward()

            torch.nn.utils.clip_grad_norm_(
                model.parameters(),
                max_norm=1.0
            )

            optimizer.step()
            scheduler.step()

            total_loss += loss.item()
            batch_count += 1

            print(
                f"Epoch {epoch + 1}/{config['epochs']} "
                f"Batch {batch_index + 1}/{len(dataloader)} "
                f"Loss: {loss.item():.4f}"
            )

        if batch_count == 0:
            raise ValueError("No valid batches in this epoch")

        average_loss = total_loss / batch_count

        writer.writerow([epoch + 1, average_loss])
        f.flush()

        print(
            f"Epoch {epoch + 1}/{config['epochs']} "
            f"Average Loss: {average_loss:.4f}"
        )

model.config.use_cache = True

model.save_pretrained(output_dir)
tokenizer.save_pretrained(output_dir)

print(f"Training completed. Model saved to {output_dir}")