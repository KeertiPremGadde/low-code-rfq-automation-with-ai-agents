"""Evaluate extraction accuracy on the 20 synthetic RFQ PDFs.

    python scripts/eval.py                 call extract_from_pdf_bytes() directly (masking ON)
    python scripts/eval.py --via-mailpit   send each PDF through Mailpit and call POST /extract

Compares with data/answer_key.json, prints a per-field table and writes docs/eval_results.md.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app.extract import extract_from_pdf_bytes, pdf_to_text  # noqa: E402
from app.masking import get_masker  # noqa: E402

KEY = ROOT / "data" / "answer_key.json"
RFQ_DIR = ROOT / "data" / "rfqs"
OUT = ROOT / "docs" / "eval_results.md"
# USD per million tokens (input, output) - from the published price list, used for the estimate only
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00), "claude-opus-5-5": (4.00, 20.00)}
STOP = set("the and for with from that this into over new set one of to in on a an is are be as by at or".split())
EXACT_FIELDS = ["customer", "site", "equipment_type", "service_type", "due_date"]


def norm(v):
    return v.strip().lower() if isinstance(v, str) else v


def keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w[:6] for w in words if len(w) > 3 and w not in STOP}  # crude stem: first 6 chars


def scope_score(expected: str, got: str) -> float:
    exp = keywords(expected)
    return len(exp & keywords(got)) / len(exp) if exp else 1.0


def missing_prf(exp: set, got: set) -> tuple[int, int, int]:
    return len(exp & got), len(got - exp), len(exp - got)  # tp, fp, fn


def masking_issues(text: str, entry: dict, masker) -> list[str]:
    """Problems caused by masking: names destroyed, or contact data not masked exactly once."""
    masked, counts = masker.mask(text)
    issues = []
    for field in ("customer", "site"):
        if entry[field] and entry[field] not in masked:
            issues.append(f"{field} '{entry[field]}' damaged by masking")
    for ent in ("EMAIL_ADDRESS", "PHONE_NUMBER"):  # every synthetic RFQ has exactly one of each
        if counts.get(ent, 0) != 1:
            issues.append(f"{ent} masked {counts.get(ent, 0)}x (expected 1)")
    if counts.get("PERSON", 0) == 0:
        issues.append("PERSON masked 0x (contact name leaked?)")
    return issues


def get_results(via_mailpit: bool, key: list[dict]) -> list[dict | Exception]:
    results = []
    if via_mailpit:
        import httpx
        import send_rfq
    for i, entry in enumerate(key, 1):
        try:
            if via_mailpit:
                send_rfq.send_rfq(entry)
                time.sleep(1.5)
                mid = httpx.get("http://localhost:8025/api/v1/messages?limit=1").json()["messages"][0]["ID"]
                r = httpx.post("http://localhost:8000/extract", json={"message_id": mid}, timeout=120)
                r.raise_for_status()
                results.append(r.json())
            else:
                results.append(extract_from_pdf_bytes((RFQ_DIR / entry["file"]).read_bytes(), message_id=entry["file"]))
        except Exception as e:  # noqa: BLE001
            results.append(e)
        print(f"  [{i:02d}/{len(key)}] {entry['file']} {'ERROR ' + type(results[-1]).__name__ if isinstance(results[-1], Exception) else 'ok'}")
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--via-mailpit", action="store_true")
    args = ap.parse_args()
    key = json.loads(KEY.read_text(encoding="utf-8"))
    masker = get_masker()
    print(f"Running extraction on {len(key)} PDFs ...")
    results = get_results(args.via_mailpit, key)

    hits = {f: 0 for f in EXACT_FIELDS}
    scope_scores, miss_f1s = [], []
    tp = fp = fn = 0
    in_tok = out_tok = 0
    models, versions = set(), set()
    mismatches, mask_issues, errors = [], [], []
    n_ok = 0
    for entry, res in zip(key, results):
        text = pdf_to_text((RFQ_DIR / entry["file"]).read_bytes())
        for issue in masking_issues(text, entry, masker):
            mask_issues.append(f"{entry['file']}: {issue}")
        if isinstance(res, Exception):
            errors.append(f"{entry['file']}: {type(res).__name__}: {str(res)[:150]}")
            scope_scores.append(0.0)
            miss_f1s.append(0.0)
            fn += len(entry["missing_info"])
            continue
        n_ok += 1
        models.add(res["model"])
        versions.add(res["prompt_version"])
        u = res.get("usage", {})
        in_tok += u.get("input_tokens", 0)
        out_tok += u.get("output_tokens", 0)
        for f in EXACT_FIELDS:
            if norm(res.get(f)) == norm(entry[f]):
                hits[f] += 1
            else:
                mismatches.append(f"{entry['file']} {f}: expected {entry[f]!r}, got {res.get(f)!r}")
        scope_scores.append(scope_score(entry["scope_summary"], res.get("scope_summary") or ""))
        exp, got = set(entry["missing_info"]), set(res["missing_info"])
        a, b, c = missing_prf(exp, got)
        tp, fp, fn = tp + a, fp + b, fn + c
        miss_f1s.append(1.0 if not exp and not got else 2 * a / (2 * a + b + c))
        if exp != got:
            mismatches.append(f"{entry['file']} missing_info: expected {sorted(exp)}, got {sorted(got)}")

    n = len(key)
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    rows = [(f, hits[f] / n, f"{hits[f]}/{n} exact") for f in EXACT_FIELDS]
    rows.append(("missing_info", sum(miss_f1s) / n, f"per-file F1; micro precision {prec:.2f}, recall {rec:.2f}"))
    rows.append(("scope_summary", sum(scope_scores) / n, "keyword overlap with answer key"))
    overall = sum(r[1] for r in rows) / len(rows)

    model = ", ".join(sorted(models)) or "n/a"
    price = next((p for m, p in PRICES.items() if m in model), None)
    cost = f"${(in_tok * price[0] + out_tok * price[1]) / 1e6:.4f}" if price else "n/a"

    lines = ["| Field | Score | Detail |", "|---|---|---|"]
    lines += [f"| {f} | {s:.0%} | {d} |" for f, s, d in rows]
    lines.append(f"| **overall** | **{overall:.0%}** | mean of the {len(rows)} fields above |")
    table = "\n".join(lines)
    print("\n" + table)
    print(f"\nPDFs ok: {n_ok}/{n}   model: {model}   prompt: {', '.join(sorted(versions)) or 'n/a'}")
    print(f"Tokens: {in_tok} in / {out_tok} out   estimated cost: {cost}")
    for title, items in [("Errors", errors), ("Mismatches", mismatches), ("Masking issues", mask_issues)]:
        print(f"\n{title}: {len(items)}")
        for x in items:
            print("  -", x)

    OUT.parent.mkdir(exist_ok=True)
    md = [f"# Extraction eval results", "",
          f"Model: `{model}`  Prompt version: `{', '.join(sorted(versions)) or 'n/a'}`  "
          f"Mode: {'via Mailpit + /extract' if args.via_mailpit else 'direct (extract_from_pdf_bytes)'}  ",
          f"PII masking: ON  PDFs: {n} ({n_ok} extracted)", "", table, "",
          f"Tokens: {in_tok} input / {out_tok} output. Estimated cost: {cost} (list price, synthetic data).", ""]
    for title, items in [("Errors", errors), ("Mismatches", mismatches), ("Masking issues", mask_issues)]:
        md += [f"## {title} ({len(items)})", ""] + ([f"- {x}" for x in items] or ["- none"]) + [""]
    OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
