
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import requests


# ============================================================
# CONFIGURATION
# ============================================================

MODEL = "phi3.5:latest"
OLLAMA_URL = "http://localhost:11434/api/generate"

REJECTED_FILE = Path("data/rejected.jsonl")
UNRESOLVED_FILE = Path("data/unresolved.json")

SHARD_FILES = [
    Path("data/teacher_shards/shard-0.jsonl"),
    Path("data/teacher_shards/shard-1.jsonl"),
]

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
SLOT_KEYS = ("date", "time", "place")

MAX_RETRIES = 5


# ============================================================
# PARSE JSON LABEL
# ============================================================

def parse_label(raw):

    if isinstance(raw, dict):
        return raw

    if not isinstance(raw, str):
        return None

    try:
        result = json.loads(raw)
        return result if isinstance(result, dict) else None

    except json.JSONDecodeError:

        match = re.search(r"\{.*\}", raw, re.DOTALL)

        if not match:
            return None

        try:
            result = json.loads(match.group())
            return result if isinstance(result, dict) else None

        except json.JSONDecodeError:
            return None


# ============================================================
# PYTHON VALIDATION
# ============================================================

def validate_label(command, label):

    if not isinstance(label, dict):
        return False, "invalid_json"

    if set(label.keys()) != EXPECTED_KEYS:
        return False, "wrong_keys"

    intent = label["intent"]

    if not isinstance(intent, str):
        return False, "intent_not_string"

    if intent not in ALLOWED_INTENTS:
        return False, "intent_not_allowed"

    for slot in SLOT_KEYS:

        value = label[slot]

        if value is None:
            continue

        if not isinstance(value, str):
            return False, f"invalid_{slot}_type"

        if not value.strip():
            return False, f"empty_{slot}"

        # EXACT CONDITION USED BY THE DATASET CLEANER
        if value.lower() not in command.lower():
            return False, f"{slot}_not_found_in_command"

    return True, "valid"


# ============================================================
# IDENTIFY INVALID SLOTS
# ============================================================

def find_invalid_slots(command, label):

    invalid_slots = []

    if not isinstance(label, dict):
        return list(SLOT_KEYS)

    for slot in SLOT_KEYS:

        value = label.get(slot)

        if value is None:
            continue

        if not isinstance(value, str) or not value.strip():
            invalid_slots.append(slot)

        elif value.lower() not in command.lower():
            invalid_slots.append(slot)

    return invalid_slots


# ============================================================
# GENERATE REPAIR USING OLLAMA
# ============================================================

def generate_repair(
    command,
    original_label,
    fields_to_repair,
    previous_error=None,
):

    command_json = json.dumps(command, ensure_ascii=False)

    label_json = json.dumps(
        original_label,
        ensure_ascii=False,
    )

    fields_json = json.dumps(
        fields_to_repair,
        ensure_ascii=False,
    )

    if fields_to_repair == ["intent"]:

        output_instruction = """
Return ONLY valid JSON containing exactly this key:

{"intent":"one_allowed_intent"}

Do not return date, time, or place.
"""

        repair_rules = """
Repair only the intent.

Understand the complete command meaning.
Choose the correct allowed intent.
Do not guess based on one keyword.
"""

    elif set(fields_to_repair) == {"intent", *SLOT_KEYS}:

        output_instruction = """
Return ONLY one JSON object with exactly these keys:

{
    "intent": "allowed_intent",
    "date": null,
    "time": null,
    "place": null
}
"""

        repair_rules = """
Repair the entire label.

Choose the correct intent.
Extract only explicit date, time, and place values.
Follow every strict substring rule below.
"""

    else:

        output_instruction = f"""
Return ONLY a JSON object containing exactly these requested fields:

{fields_json}

Do not return any additional keys.
"""

        repair_rules = f"""
Repair ONLY these fields:

{fields_json}

Keep every other field from ORIGINAL LABEL unchanged.

If a requested slot cannot be extracted as an exact substring,
return null for that slot.
"""

    retry_instruction = ""

    if previous_error:

        retry_instruction = f"""
============================================================
PREVIOUS VALIDATION FAILURE
============================================================

Your previous answer failed the Python validator.

Exact validation feedback:

{previous_error}

You MUST correct this failure.

Do not repeat the previously rejected value.

Read the original command again.

For a failing slot:
1. Find the exact phrase inside COMMAND.
2. Copy that exact phrase.
3. Do not add or remove punctuation.
4. Do not change word order.
5. Do not convert the phrase to another representation.
6. If no appropriate exact phrase exists, use null.

Your next response must pass the Python validation condition.
"""

    prompt = f"""
You are an expert command-parsing dataset label REPAIR system.

Your responsibility is to produce labels that are BOTH:

1. Semantically correct according to the command.
2. Valid under the exact Python validation condition.

Do not prioritize filling slots over correctness.

============================================================
COMMAND
============================================================

{command_json}

============================================================
ORIGINAL LABEL
============================================================

{label_json}

============================================================
FIELDS TO REPAIR
============================================================

{fields_json}

============================================================
CRITICAL PYTHON VALIDATION CONDITION
============================================================

The dataset cleaner uses this exact condition:

    value.lower() in command.lower()

This condition is used for every non-null date, time, and place.

THIS CONDITION MUST EVALUATE TO TRUE.

The validator performs a literal continuous substring check.

It does NOT:
- Understand synonyms.
- Normalize dates.
- Convert written numbers to digits.
- Convert digits to written numbers.
- Add or remove punctuation.
- Insert commas.
- Correct spelling.
- Interpret semantic equivalence.

For example:

Command:
"what time does the sun set"

The value "sunset" FAILS.

The value "sun set" PASSES.

The reason is:

    "sunset" in "what time does the sun set"       -> False

    "sun set" in "what time does the sun set"      -> True

The Python validator ignores case, but it does NOT ignore
spaces, punctuation, spelling, or word order.

============================================================
STRICT DATE EXTRACTION
============================================================

Extract only date expressions explicitly present
in the original command.

Examples:

Command:
"set an alarm for tomorrow"

Correct:
"date": "tomorrow"

Command:
"schedule an event next friday"

Correct:
"date": "next friday"

Command:
"remind me on january second"

Correct:
"date": "january second"

Command:
"please tell me current events for the day"

Correct:
"date": null

Do not infer "today" from "the day".

Do not convert "tomorrow" to a calendar date.

Do not convert "march sixteen" into "March 16".

Do not infer a date from the current date.

If the date expression is not explicitly present,
return null.

============================================================
STRICT TIME EXTRACTION
============================================================

Extract only explicit time expressions.

Examples:

Command:
"set alarm for 7 pm"

Correct:
"time": "7 pm"

Command:
"set alarm for seven pm"

Correct:
"time": "seven pm"

Command:
"remind me in ten minutes"

Correct:
"time": "in ten minutes"

Command:
"what time does the sun set"

Correct:
"time": "sun set"

Do not convert "seven pm" to "19:00".

Do not convert "7 pm" to "7:00 PM".

Do not infer a time from an event.

Do not return "now" unless the word "now"
actually appears in the command.

If no explicit time exists, return null.

============================================================
STRICT PLACE EXTRACTION
============================================================

Extract only an explicitly stated location,
destination, or venue.

Copy the exact continuous phrase from the command.

Examples:

Command:
"what is the weather in Imphal"

Correct:
"place": "Imphal"

Command:
"weather in Imphal, Manipur"

Correct:
"place": "Imphal, Manipur"

Command:
"weather in brooklyn new york"

Correct:
"place": "brooklyn new york"

Incorrect:
"place": "Brooklyn, New York"

Reason:
The comma is not present in the command.

Command:
"find events near me"

Correct:
"place": null

Command:
"what is the time difference between here and dakar"

Correct:
"place": "dakar"

Incorrect:
"place": "here,dakar"

Reason:
"here,dakar" is not an exact substring.
"dakar" is explicitly present as a named location.

Do not infer:
- A state from a city.
- A country from a state.
- A city from a country.
- A place from external geographic knowledge.
- A place from the original label if it is absent in COMMAND.

Do not add commas or combine separate locations
with punctuation that does not exist in the command.

If no appropriate explicit location exists, return null.

============================================================
GENERAL SLOT RULES
============================================================

For every requested slot:

1. Read COMMAND carefully.
2. Understand the meaning of the command.
3. Identify the explicit expression representing the slot.
4. Copy the expression as an exact continuous substring.
5. Verify that the expression occurs in COMMAND.
6. Use null if no valid explicit expression exists.

Never invent information.

Never paraphrase.

Never normalize.

Never translate.

Never convert numbers.

Never replace a phrase with a synonym.

Never return a value merely because it is semantically related.

A slot that is semantically correct but fails the substring
condition is INVALID.

A slot that passes the substring condition but is
semantically incorrect is also INVALID.

Both conditions are mandatory.

============================================================
INTENT CLASSIFICATION
============================================================

Allowed intents:

alarm_set:
The user wants to create or set an alarm.

alarm_query:
The user asks about existing alarms.

calendar_set:
The user wants to create, schedule, or add an event,
appointment, meeting, or reminder.

calendar_query:
The user asks about existing calendar events.

calendar_remove:
The user wants to cancel, delete, or remove a calendar event.

weather_query:
The user asks about weather, temperature, rain,
snow, or forecasts.

datetime_query:
The user asks about the current date, time, or day.

recommendation_events:
The user asks for recommendations, events, activities,
concerts, games, or things to attend.

Understand the complete command.

Select exactly one allowed intent.

A date or time mention alone does not imply calendar_set.

Do not change a valid original intent unless intent
is one of the requested fields to repair.

============================================================
FINAL SELF-CHECK
============================================================

Before returning the JSON, perform these checks.

CHECK 1:
Does the JSON contain exactly the requested fields?

CHECK 2:
Is the intent valid if intent is requested?

CHECK 3:
Is every non-null slot a string?

CHECK 4:
Is every non-null slot an exact continuous substring
of COMMAND?

CHECK 5:
For every non-null slot, mentally evaluate:

    value.lower() in command.lower()

CHECK 6:
Does every non-null slot have the correct meaning?

CHECK 7:
Did you add any comma, synonym, normalization,
inferred date, inferred time, or inferred place?

If any slot fails either substring correctness
or semantic correctness, repair it or return null.

{repair_rules}

{retry_instruction}

============================================================
OUTPUT
============================================================

{output_instruction}

Return valid JSON only.

No markdown.
No comments.
No explanations.
No text outside the JSON.
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0,
                "num_ctx": 4096,
            },
        },
        timeout=(10, 180),
    )

    response.raise_for_status()

    return response.json()["response"]


# ============================================================
# LOAD REJECTED RECORDS
# ============================================================

def load_rejected_records():

    records_by_id = {}

    with REJECTED_FILE.open("r", encoding="utf-8") as file:

        for line in file:

            if not line.strip():
                continue

            item = json.loads(line)

            reason = item.get("rejection_reason", "")

            # Duplicate commands do not need regeneration.
            if reason == "duplicate_command":
                continue

            record = item.get("record")

            if not isinstance(record, dict):
                continue

            record_id = record.get("id")
            command = record.get("text")

            original_label = parse_label(
                record.get("teacher_raw")
            )

            if not record_id or not isinstance(command, str):
                continue

            if not isinstance(original_label, dict):

                fields_to_repair = [
                    "intent",
                    *SLOT_KEYS,
                ]

            else:

                fields_to_repair = find_invalid_slots(
                    command,
                    original_label,
                )

                intent = original_label.get("intent")

                if (
                    not isinstance(intent, str)
                    or intent not in ALLOWED_INTENTS
                ):
                    fields_to_repair.insert(0, "intent")

                if set(original_label) != EXPECTED_KEYS:

                    fields_to_repair = [
                        "intent",
                        *SLOT_KEYS,
                    ]

            if not fields_to_repair:
                continue

            records_by_id[record_id] = {
                "id": record_id,
                "text": command,
                "reason": reason,
                "original_label": original_label,
                "fields_to_repair": list(
                    dict.fromkeys(fields_to_repair)
                ),
            }

    return list(records_by_id.values())


# ============================================================
# MERGE REPAIRED FIELDS
# ============================================================

def merge_repaired_fields(
    original_label,
    repaired_fields,
    fields_to_repair,
):

    if set(fields_to_repair) == {"intent", *SLOT_KEYS}:

        if set(repaired_fields) != EXPECTED_KEYS:
            return None

        return repaired_fields

    if not isinstance(original_label, dict):
        return None

    merged = dict(original_label)

    for field in fields_to_repair:

        if field not in repaired_fields:
            return None

        merged[field] = repaired_fields[field]

    return merged


# ============================================================
# MAIN REGENERATION PROCESS
# ============================================================

def main():

    if not REJECTED_FILE.exists():

        raise FileNotFoundError(
            f"Rejected file not found: {REJECTED_FILE}"
        )

    for shard_path in SHARD_FILES:

        if not shard_path.exists():

            raise FileNotFoundError(
                f"Shard file not found: {shard_path}"
            )

    rejected_records = load_rejected_records()

    print(
        f"Invalid records to regenerate: "
        f"{len(rejected_records)}"
    )

    corrected = {}
    unresolved = []

    # --------------------------------------------------------
    # REGENERATE LABELS
    # --------------------------------------------------------

    for index, item in enumerate(
        rejected_records,
        start=1,
    ):

        record_id = item["id"]
        command = item["text"]

        original_label = item["original_label"]

        fields_to_repair = item["fields_to_repair"]

        print(
            f"\n[{index}/{len(rejected_records)}] "
            f"Processing {record_id}"
        )

        print(
            f"Fields to repair: "
            f"{', '.join(fields_to_repair)}"
        )

        previous_error = None
        valid_label = None

        for attempt in range(1, MAX_RETRIES + 1):

            try:

                print(
                    f"  Attempt {attempt}/{MAX_RETRIES}"
                )

                raw = generate_repair(
                    command,
                    original_label,
                    fields_to_repair,
                    previous_error,
                )

                repaired_fields = parse_label(raw)

                if not isinstance(repaired_fields, dict):

                    previous_error = (
                        "invalid_json: "
                        "response must be a JSON object"
                    )

                    print(
                        f"  Validation failed: "
                        f"{previous_error}"
                    )

                    continue

                merged_label = merge_repaired_fields(
                    original_label,
                    repaired_fields,
                    fields_to_repair,
                )

                valid, reason = validate_label(
                    command,
                    merged_label,
                )

                if valid:

                    valid_label = json.dumps(
                        merged_label,
                        ensure_ascii=False,
                    )

                    print(
                        f"  Corrected: {record_id}"
                    )

                    break

                previous_error = reason

                # Provide the exact failed slot and value.
                if isinstance(merged_label, dict):

                    failed_slot = next(
                        (
                            slot
                            for slot in fields_to_repair
                            if slot in SLOT_KEYS
                            and merged_label.get(slot) is not None
                            and (
                                not isinstance(
                                    merged_label.get(slot),
                                    str,
                                )
                                or merged_label.get(slot).lower()
                                not in command.lower()
                            )
                        ),
                        None,
                    )

                    if failed_slot:

                        failed_value = merged_label.get(
                            failed_slot
                        )

                        previous_error = (
                            f"{reason}. The attempted "
                            f"{failed_slot} value "
                            f"{failed_value!r} is not an exact "
                            f"substring of COMMAND "
                            f"{command!r}. "
                            f"Do not repeat {failed_value!r}. "
                            f"Return a different exact substring "
                            f"from COMMAND for {failed_slot}, "
                            f"or null if no explicit value exists."
                        )

                print(
                    f"  Validation failed: {reason}"
                )

            except requests.RequestException as error:

                previous_error = (
                    f"request_error: {error}"
                )

                print(
                    f"  Ollama request failed: {error}"
                )

            except Exception as error:

                previous_error = (
                    f"unexpected_error: {error}"
                )

                print(
                    f"  Error: {error}"
                )

        if valid_label is not None:

            corrected[record_id] = valid_label

        else:

            unresolved.append(record_id)

            print(
                f"  Unresolved after {MAX_RETRIES} attempts: "
                f"{record_id}"
            )

    # --------------------------------------------------------
    # BACKUP AND UPDATE SHARDS
    # --------------------------------------------------------

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    total_updated = 0

    if corrected:

        # Create backups before modifying any shard.
        for shard_path in SHARD_FILES:

            backup_path = shard_path.with_name(
                f"{shard_path.stem}_{timestamp}.bak"
            )

            shutil.copy2(
                shard_path,
                backup_path,
            )

            print(
                f"Backup created: {backup_path}"
            )

        # Update corrected records.
        for shard_path in SHARD_FILES:

            updated_lines = []
            shard_updated = 0

            with shard_path.open(
                "r",
                encoding="utf-8",
            ) as file:

                for line in file:

                    if not line.strip():
                        continue

                    record = json.loads(line)

                    record_id = record.get("id")

                    if record_id in corrected:

                        record["teacher_raw"] = corrected[
                            record_id
                        ]

                        shard_updated += 1

                    updated_lines.append(
                        json.dumps(
                            record,
                            ensure_ascii=False,
                        )
                    )

            temp_path = shard_path.with_suffix(
                shard_path.suffix + ".tmp"
            )

            with temp_path.open(
                "w",
                encoding="utf-8",
            ) as file:

                file.write(
                    "\n".join(updated_lines) + "\n"
                )

            temp_path.replace(shard_path)

            total_updated += shard_updated

            print(
                f"Updated shard: {shard_path} "
                f"({shard_updated} records)"
            )

    # --------------------------------------------------------
    # SAVE UNRESOLVED IDS
    # --------------------------------------------------------

    UNRESOLVED_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    UNRESOLVED_FILE.write_text(
        json.dumps(
            unresolved,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print("\n========== SUMMARY ==========")

    print(
        f"Invalid records processed: "
        f"{len(rejected_records)}"
    )

    print(
        f"Valid regenerated labels: "
        f"{len(corrected)}"
    )

    print(
        f"Shard records updated: "
        f"{total_updated}"
    )

    print(
        f"Unresolved records: "
        f"{len(unresolved)}"
    )

    print(
        f"Unresolved IDs saved to: "
        f"{UNRESOLVED_FILE}"
    )


if __name__ == "__main__":
    main()
