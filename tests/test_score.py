import json
import unittest
from pathlib import Path

from jsonschema import ValidationError, validate

from training.score import extract_json

ROOT = Path(__file__).resolve().parent.parent

with open(ROOT / "service" / "schema.json", "r", encoding="utf-8") as f:
    SCHEMA = json.load(f)["json_schema"]


class TestScore(unittest.TestCase):

    def test_extract_valid_json(self):
        text = '{"intent": "calendar_remove", "date": null, "time": null, "place": null}'

        result = extract_json(text)

        self.assertIsNotNone(result)
        self.assertEqual(result["intent"], "calendar_remove")

    def test_extract_invalid_json(self):
        text = "{invalid json}"

        result = extract_json(text)

        self.assertIsNone(result)

    def test_valid_schema_prediction(self):
        prediction = {
            "intent": "calendar_remove",
            "date": None,
            "time": None,
            "place": None
        }

        validate(instance=prediction, schema=SCHEMA)

    def test_invalid_schema_prediction(self):
        prediction = {
            "intent": "invalid_intent",
            "date": None,
            "time": None,
            "place": None
        }

        with self.assertRaises(ValidationError):
            validate(instance=prediction, schema=SCHEMA)


if __name__ == "__main__":
    unittest.main()
