"""Core extraction: PDF bytes -> masked text -> LLM -> validated fields. Used by the API and by eval."""
import io
import os
from datetime import datetime, timezone

from pydantic import ValidationError
from pypdf import PdfReader

from .llm import LLMError, get_provider
from .logging_utils import log_llm_call
from .masking import get_masker
from .schemas import Extraction


def pdf_to_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((p.extract_text() or "") for p in reader.pages).strip()


def extract_from_pdf_bytes(pdf_bytes: bytes, message_id: str | None = None) -> dict:
    """Return the extracted fields plus model, prompt_version, extracted_at, mailpit_id and usage."""
    prompt_version = os.getenv("PROMPT_VERSION", "extract-v1")
    text = pdf_to_text(pdf_bytes)
    masked, counts = get_masker().mask(text)
    provider = get_provider()
    try:
        res = provider.extract(masked)
        fields = Extraction.model_validate(res.data)
    except (LLMError, ValidationError) as e:
        log_llm_call(message_id=message_id, model=provider.model, prompt_version=prompt_version, latency_ms=0,
                     input_tokens=0, output_tokens=0, masked_counts=counts, ok=False, error=type(e).__name__)
        raise
    log_llm_call(message_id=message_id, model=res.model, prompt_version=prompt_version, latency_ms=res.latency_ms,
                 input_tokens=res.input_tokens, output_tokens=res.output_tokens, masked_counts=counts)
    out = fields.model_dump(mode="json")  # due_date -> ISO string
    out["missing_info_text"] = ", ".join(out["missing_info"])
    out.update(
        model=res.model,
        prompt_version=prompt_version,
        extracted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        mailpit_id=message_id,
        usage={"input_tokens": res.input_tokens, "output_tokens": res.output_tokens,
               "latency_ms": res.latency_ms, "masked_counts": counts},
    )
    return out
