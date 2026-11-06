"""Read access to Baserow for the /ask agent (database token auth, run from Windows via localhost)."""
import os
import re

import httpx

PASTBID_FIELDS = ["bid_id", "customer", "equipment_type", "service_type", "scope", "price_band", "year", "outcome"]
STOPWORDS = {"the", "and", "for", "did", "we", "our", "any", "all", "with", "from", "that", "what", "which"}


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=os.getenv("BASEROW_URL", "http://localhost:8081").rstrip("/"),
        headers={"Authorization": f"Token {os.environ['BASEROW_TOKEN']}"},
        timeout=30,
    )


def _flat(v):
    """Baserow single select -> its text; multiple select -> list of texts; everything else unchanged."""
    if isinstance(v, dict) and "value" in v:
        return v["value"]
    if isinstance(v, list):
        return [_flat(x) for x in v]
    return v


def _tokens(keywords: list[str] | None) -> list[str]:
    out: list[str] = []
    for k in keywords or []:
        out += [w for w in re.split(r"\s+", k.lower().strip()) if len(w) >= 3 and w not in STOPWORDS]
    return out


def search_past_bids(keywords: list[str] | None = None, equipment_type: str | None = None,
                     service_type: str | None = None, limit: int = 20) -> dict:
    """Filter PastBids by equipment/service type (server-side), then rank by keyword hits (client-side).

    Keywords are matched case-insensitively against bid_id, customer, scope, price_band, year and outcome;
    a row needs at least one keyword hit, and rows with more hits come first. No keywords = no keyword filter.
    """
    params = {"user_field_names": "true", "size": 200}
    if equipment_type:
        params["filter__equipment_type__contains"] = equipment_type
    if service_type:
        params["filter__service_type__contains"] = service_type
    with _client() as c:
        r = c.get(f"/api/database/rows/table/{os.environ['BASEROW_PASTBIDS_TABLE_ID']}/", params=params)
        r.raise_for_status()
    rows = [{f: _flat(row.get(f)) for f in PASTBID_FIELDS} for row in r.json()["results"]]

    toks = _tokens(keywords)
    if toks:
        scored = []
        for row in rows:
            text = " ".join(str(row[f]) for f in ("bid_id", "customer", "scope", "price_band", "year", "outcome")).lower()
            hits = sum(1 for t in toks if t in text)
            if hits:
                scored.append((hits, row))
        scored.sort(key=lambda x: (-x[0], -int(x[1]["year"] or 0)))
        rows = [row for _, row in scored]
    return {"count": len(rows), "returned": min(len(rows), limit), "rows": rows[:limit]}


def get_rfq(row_id: int) -> dict:
    """One row from the RFQs table by its Baserow row id (the 'id' / row number)."""
    with _client() as c:
        r = c.get(f"/api/database/rows/table/{os.environ['BASEROW_RFQS_TABLE_ID']}/{int(row_id)}/",
                  params={"user_field_names": "true"})
        if r.status_code == 404:
            return {"error": f"no RFQ row with id {row_id}"}
        r.raise_for_status()
    row = {k: _flat(v) for k, v in r.json().items() if k != "order"}
    return row


def list_rfq_ids() -> list[int]:
    """Row ids present in RFQs (used by scripts/ask_demo.py to pick real rows)."""
    with _client() as c:
        r = c.get(f"/api/database/rows/table/{os.environ['BASEROW_RFQS_TABLE_ID']}/",
                  params={"user_field_names": "true", "size": 200})
        r.raise_for_status()
    return [row["id"] for row in r.json()["results"]]
