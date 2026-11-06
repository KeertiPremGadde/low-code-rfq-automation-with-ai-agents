"""Set up Baserow for BidDesk (stdlib + httpx, run from the project root).

    python scripts/setup_baserow.py [--url http://localhost:8081]

Reads BASEROW_ADMIN_EMAIL and BASEROW_ADMIN_PASSWORD from .env (no defaults, nothing on the command line).

What it does:
  1. Logs in with that e-mail/password (JWT). If the account does not exist yet it is registered
     (the first Baserow user becomes admin).
  2. Creates database "BidDesk" with tables RFQs and PastBids (typed fields, single-select options).
  3. Imports data/past_bids.csv into PastBids.
  4. Creates a database token and prints the values to paste into .env.

Safe to re-run: an existing "BidDesk" database is reused and existing tables are skipped.
"""
import argparse
import csv
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://localhost:8081"

STATUS_OPTIONS = [
    {"value": "Awaiting approval", "color": "light-orange"},
    {"value": "Approved", "color": "light-green"},
    {"value": "Rejected", "color": "light-red"},
]
SERVICE_OPTIONS = [{"value": v, "color": c} for v, c in
                   [("inspection", "light-blue"), ("overhaul", "light-orange"),
                    ("upgrade", "light-green"), ("spare parts", "light-gray")]]
EQUIPMENT_OPTIONS = [{"value": v, "color": c} for v, c in
                     [("heavy-duty gas turbine", "light-blue"), ("aeroderivative gas turbine", "light-green"),
                      ("compressor", "light-orange"), ("generator", "light-red"),
                      ("combustion parts", "light-gray")]]
OUTCOME_OPTIONS = [{"value": v, "color": c} for v, c in
                   [("Won", "light-green"), ("Lost", "light-red"), ("No bid", "light-gray")]]
PRICE_BANDS = ["<50k EUR", "50-150k EUR", "150-500k EUR", "500k-1M EUR", ">1M EUR"]

DATETIME = {"type": "date", "date_format": "ISO", "date_include_time": True, "date_time_format": "24"}

# First column is the primary field (created with the table); the rest are added one by one.
RFQS = {
    "primary": "customer",
    "fields": [
        {"name": "site", "type": "text"},
        {"name": "equipment_type", "type": "single_select", "select_options": EQUIPMENT_OPTIONS},
        {"name": "service_type", "type": "single_select", "select_options": SERVICE_OPTIONS},
        {"name": "due_date", **DATETIME},  # include_time on (matches the flow's DATE_TIME mapping)
        {"name": "scope_summary", "type": "long_text"},
        {"name": "missing_info", "type": "long_text"},
        {"name": "status", "type": "single_select", "select_options": STATUS_OPTIONS},
        {"name": "model", "type": "text"},
        {"name": "prompt_version", "type": "text"},
        {"name": "extracted_at", **DATETIME},
        {"name": "approved_by", "type": "text"},
        {"name": "mailpit_id", "type": "text"},
    ],
}
PASTBIDS = {
    "primary": "bid_id",
    "fields": [
        {"name": "customer", "type": "text"},
        {"name": "equipment_type", "type": "single_select", "select_options": EQUIPMENT_OPTIONS},
        {"name": "service_type", "type": "single_select", "select_options": SERVICE_OPTIONS},
        {"name": "scope", "type": "long_text"},
        {"name": "price_band", "type": "single_select",
         "select_options": [{"value": v, "color": "light-blue"} for v in PRICE_BANDS]},
        {"name": "year", "type": "number", "number_decimal_places": 0, "number_negative": False},
        {"name": "outcome", "type": "single_select", "select_options": OUTCOME_OPTIONS},
    ],
}


def check(r: httpx.Response) -> dict:
    if r.status_code >= 400:
        sys.exit(f"Baserow error {r.status_code} on {r.request.method} {r.request.url}\n{r.text[:600]}")
    return r.json() if r.content else {}


def login(c: httpx.Client, email: str, password: str) -> str:
    r = c.post("/api/user/token-auth/", json={"email": email, "password": password})
    if r.status_code == 401 or r.status_code == 400:
        print("Login failed - trying to register this account (first user becomes admin)...")
        check(c.post("/api/user/", json={"name": "BidDesk Admin", "email": email, "password": password,
                                         "language": "en", "authenticate": False}))
        r = c.post("/api/user/token-auth/", json={"email": email, "password": password})
    data = check(r)
    return data.get("access_token") or data["token"]


def create_table(c: httpx.Client, db_id: int, name: str, spec: dict) -> int:
    # one header row => table with a single text field (the primary) and no rows
    t = check(c.post(f"/api/database/tables/database/{db_id}/",
                     json={"name": name, "data": [[spec["primary"]]], "first_row_header": True}))
    table_id = t["id"]
    for f in spec["fields"]:
        check(c.post(f"/api/database/fields/table/{table_id}/", json=f))
    print(f"  created table {name} (id {table_id}) with {len(spec['fields']) + 1} fields")
    return table_id


def main() -> None:
    load_dotenv(ROOT / ".env")
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=os.getenv("BASEROW_URL") or BASE)
    a = p.parse_args()

    email = os.getenv("BASEROW_ADMIN_EMAIL", "").strip()
    password = os.getenv("BASEROW_ADMIN_PASSWORD", "")
    if not email or not password or password.startswith("CHANGE_ME"):
        sys.exit("Set BASEROW_ADMIN_EMAIL and BASEROW_ADMIN_PASSWORD in .env first (choose your own password; "
                 "if Baserow already has an account, use its login). See .env.example.")

    with httpx.Client(base_url=a.url, timeout=60) as c:
        c.headers["Authorization"] = f"JWT {login(c, email, password)}"
        print(f"Logged in as {email}")

        workspaces = check(c.get("/api/workspaces/"))
        if not workspaces:
            workspaces = [check(c.post("/api/workspaces/", json={"name": "BidDesk"}))]
        ws = workspaces[0]
        print(f"Workspace: {ws['name']} (id {ws['id']})")

        apps = check(c.get("/api/applications/"))
        db = next((x for x in apps if x["type"] == "database" and x["name"] == "BidDesk"
                   and x["workspace"]["id"] == ws["id"]), None)
        if db is None:
            db = check(c.post(f"/api/applications/workspace/{ws['id']}/", json={"name": "BidDesk", "type": "database"}))
            print(f"Created database BidDesk (id {db['id']})")
        else:
            print(f"Reusing database BidDesk (id {db['id']})")

        existing = {t["name"]: t["id"] for t in check(c.get(f"/api/database/tables/database/{db['id']}/"))}
        new_pastbids = "PastBids" not in existing
        rfqs_id = existing.get("RFQs") or create_table(c, db["id"], "RFQs", RFQS)
        pb_id = existing.get("PastBids") or create_table(c, db["id"], "PastBids", PASTBIDS)

        if new_pastbids:
            with (ROOT / "data" / "past_bids.csv").open(encoding="utf-8", newline="") as f:
                items = [{**row, "year": int(row["year"])} for row in csv.DictReader(f)]
            check(c.post(f"/api/database/rows/table/{pb_id}/batch/?user_field_names=true", json={"items": items}))
            print(f"  imported {len(items)} past bids")
        else:
            print("  PastBids already existed - import skipped")

        tok = check(c.post("/api/database/tokens/", json={"name": "biddesk-service", "workspace": ws["id"]}))

    print("\nDone. Paste these into .env (replace the empty values):\n")
    print(f"BASEROW_TOKEN={tok['key']}")
    print(f"BASEROW_RFQS_TABLE_ID={rfqs_id}")
    print(f"BASEROW_PASTBIDS_TABLE_ID={pb_id}")
    print(f"\nBaserow UI: {a.url}  login: {email} (password from .env)")


if __name__ == "__main__":
    main()
