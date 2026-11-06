"""Append-only audit log of every LLM call: logs/llm_calls.jsonl.

Only metadata is written - never the PDF text, the prompt or the model output, so no PII.
"""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "llm_calls.jsonl"
_lock = threading.Lock()


def log_llm_call(*, message_id: str | None, model: str, prompt_version: str, latency_ms: int,
                 input_tokens: int, output_tokens: int, masked_counts: dict[str, int],
                 ok: bool = True, error: str | None = None, extra: dict | None = None) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "message_id": message_id,
        "model": model,
        "prompt_version": prompt_version,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "masked_counts": masked_counts,
        "ok": ok,
    }
    if error:
        entry["error"] = error[:200]
    if extra:
        entry.update(extra)  # e.g. endpoint, tools_used - metadata only, never question/answer text
    LOG_PATH.parent.mkdir(exist_ok=True)
    with _lock, LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
