"""Source-backed catalogue lookup. Missing parts return None, never invented prices."""
import csv
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"


def _key(value: str) -> str:
    return " ".join(value.lower().replace("_", " ").replace("-", " ").split())


def part_price(model: str, part: str) -> dict | None:
    """Demo catalogue defaults; inspect fitment_note before applying to a real VIN."""
    with (DATA / "prices.csv").open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if _key(row["model"]) == _key(model) and _key(row["part"]) == _key(part):
                return {**row, "price": float(row["price"])}
    return None


def labour_range(part: str, action: str) -> tuple[int, int]:
    """INR assumptions; unknown operations require a garage quote (KeyError)."""
    table = json.loads((DATA / "labour.json").read_text())
    return tuple(table[_key(part).replace(" ", "_")][action.strip().lower()])
