"""Monthly meter report. Standard library only; settings are the repair surface."""
import csv
import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path
import sys


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate configuration key")
        result[key] = value
    return result


def money(value):
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def generate(config_path):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"),
                        object_pairs_hook=pairs)
    expected = {"encoding", "delimiter", "currency", "input", "output"}
    if set(config) != expected or config["currency"] != "RUB":
        raise ValueError("configuration schema")
    if config["encoding"] not in ("utf-8", "cp1251"):
        raise ValueError("unsupported encoding")
    if config["delimiter"] not in (",", ";"):
        raise ValueError("unsupported delimiter")
    if config["input"] != "readings.csv" or config["output"] != "report.json":
        raise ValueError("configuration path outside this job")
    meters, dates, seen = {}, [], set()
    with open(config["input"], encoding=config["encoding"], newline="") as stream:
        reader = csv.DictReader(stream, delimiter=config["delimiter"])
        if reader.fieldnames != ["date", "meter", "customer", "kwh", "rate"]:
            raise ValueError("CSV columns; check delimiter")
        for row in reader:
            if None in row or any(v is None or not v for v in row.values()):
                raise ValueError("incomplete reading")
            date = datetime.date.fromisoformat(row["date"])
            key = (date, row["meter"])
            if key in seen or len(seen) >= 100:
                raise ValueError("duplicate or excessive readings")
            seen.add(key)
            kwh, rate = Decimal(row["kwh"]), Decimal(row["rate"])
            if not kwh.is_finite() or not rate.is_finite() or kwh < 0 or rate <= 0:
                raise ValueError("invalid reading amount")
            total = meters.setdefault(row["meter"], {
                "customer": row["customer"], "kwh": Decimal(0), "amount": Decimal(0)})
            if total["customer"] != row["customer"]:
                raise ValueError("meter customer changed")
            total["kwh"] += kwh
            total["amount"] += (kwh * rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
            dates.append(date)
    if not dates:
        raise ValueError("no readings")
    report = {"currency": "RUB", "records": len(seen),
              "period": {"from": str(min(dates)), "to": str(max(dates))},
              "total_kwh": money(sum(v["kwh"] for v in meters.values())),
              "total_amount": money(sum(v["amount"] for v in meters.values())),
              "meters": [{"meter": key, "customer": value["customer"],
                          "kwh": money(value["kwh"]), "amount": money(value["amount"])}
                         for key, value in sorted(meters.items())]}
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    Path(config["output"]).write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: report.py settings.json")
    try:
        generate(sys.argv[1])
    except (OSError, UnicodeError, ValueError, InvalidOperation, csv.Error) as error:
        print(f"REPORT_FAILED: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(2)
