"""BidDesk API.  Run:  uvicorn app.main:app --host 0.0.0.0 --port 8000"""
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from . import mailpit
from .extract import extract_from_pdf_bytes
from .llm import LLMError, get_provider
from .masking import get_masker
from .agent import AgentError, ask as run_agent
from .schemas import AskRequest, ExtractRequest

log = logging.getLogger("biddesk")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_masker()  # load Presidio/spaCy once
    get_provider()
    log.info("BidDesk ready")
    yield


app = FastAPI(title="BidDesk", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": os.getenv("LLM_EXTRACT_MODEL"), "prompt_version": os.getenv("PROMPT_VERSION"),
            "provider": os.getenv("LLM_PROVIDER", "anthropic"),
            # True = forced tool_choice accepted; False = model rejected it, using auto + instruction
            "forced_tool_choice": getattr(get_provider(), "_forced", None)}


@app.post("/extract")
def extract(req: ExtractRequest) -> dict:
    try:
        found = mailpit.get_pdf(req.message_id)
    except httpx.HTTPStatusError as e:
        raise HTTPException(404 if e.response.status_code == 404 else 502, f"Mailpit: {e.response.status_code} (message_id={req.message_id!r})")
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Mailpit unreachable: {type(e).__name__}")
    if found is None:
        return {"skipped": True, "reason": "no pdf"}
    pdf_bytes, _filename = found
    try:
        result = extract_from_pdf_bytes(pdf_bytes, message_id=req.message_id)
    except (LLMError, ValidationError) as e:
        raise HTTPException(502, f"Extraction failed: {type(e).__name__}")
    return {"skipped": False, **result}


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    try:
        return run_agent(req.question)
    except AgentError as e:
        raise HTTPException(502, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Baserow unreachable: {type(e).__name__}")
