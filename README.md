# Low-Code Request for Quotation (RFQ) Automation with AI Agents

Fictional company: **Nordwind Turbine Services**. Every customer, site, person, e-mail address, phone number and bid in this repo is invented.

## The problem

Requests for quotation (RFQs) arrive as e-mails with a PDF attached. Someone opens each one, retypes the customer, site, equipment, service type and due date into a tracker, notices what is missing, and tells the bid manager. It is slow, error-prone and nobody can see what is waiting for a decision.

BidDesk automates the retyping and keeps the decision with a person:

1. An RFQ e-mail arrives.
2. A no-code flow picks it up, sends the PDF through an AI extraction step, and writes a row to a table with status **Awaiting approval**.
3. The bid manager gets a notification e-mail and works through a filtered **Approval queue** view.
4. Anyone on the bid team can ask questions of the past-bid history in plain language (`/ask`), with every answer citing bid ids.

## Architecture

```mermaid
flowchart LR
    M["RFQ e-mail + PDF"] --> MP["Mailpit<br/>(test mail server)"]
    MP -- "webhook on every new mail" --> AP["Activepieces flow<br/>(low-code)"]
    AP -- "POST /extract" --> API["FastAPI service"]
    API -- "download PDF" --> MP
    API --> MASK["Presidio masking<br/>names, e-mails, phones"]
    MASK --> LLM["Claude Haiku 5.5<br/>forced tool call"]
    API -. "metadata only" .-> LOG[("llm_calls.jsonl")]
    AP -- "create row" --> BR[("Baserow<br/>RFQs + PastBids")]
    AP -- "notification e-mail" --> MP
    BR --> Q["Approval queue view<br/>(filtered grid)"]
    ASK["POST /ask<br/>Claude Sonnet 5.5 agent"] --> BR
    ASK -. "metadata only" .-> LOG
```

## What is low-code here

Most of the business logic is configured, not coded:

| Piece | Tool | What you configure |
|---|---|---|
| The intake flow | **Activepieces** (open-source automation) | A 5-step flow: Catch Webhook -> Router (subject starts with "RFQ") -> HTTP request -> Create Baserow row -> Send e-mail. Exported to [`activepieces/biddesk_flow.json`](activepieces/biddesk_flow.json). |
| The data model | **Baserow** (open-source no-code database) | Two tables with typed fields: `RFQs` (single-select status, date-time, long text) and `PastBids` (single selects for equipment, service type, price band and outcome). Created by a script, editable in the UI. |
| The approval queue | Baserow view | A Grid view named "Approval queue" filtered on `status = Awaiting approval`. The bid manager approves by changing the status and typing their name into `approved_by`. |
| Notifications | Activepieces SMTP step | E-mail to the bid manager with customer, site, equipment, service, due date and what is missing. |

A business user can change the Router condition, the target table, the field mapping or the e-mail text without touching Python. See the [citizen developer guide](docs/citizen-developer-guide.md).

## The code parts

Only the parts that need real code are code:

- **`POST /extract`** (`app/extract.py`): downloads the PDF from Mailpit, extracts the text, masks personal data, asks Claude Haiku 5.5 for a structured result through a forced tool call, validates it with Pydantic and returns the fields plus `model`, `prompt_version` and `extracted_at`. If the mail has no PDF it returns `{"skipped": true, "reason": "no pdf"}`. Instructions to the model: do not guess; null plus `missing_info` when a detail is not in the text.
- **PII masking** (`app/masking.py`): Presidio masks `PERSON`, `EMAIL_ADDRESS` and `PHONE_NUMBER` before anything leaves for the model. Customer, site and unit names come from an allow-list (`data/allowlist.json`) so they are not mistaken for people. Entity counts are logged, the values never are.
- **`POST /ask`** (`app/agent.py`): a Claude Sonnet 5.5 agent with two tools, `search_past_bids` and `get_rfq`, that reads Baserow. It answers only from tool results, cites `bid_id`s, says so when nothing matches and never invents prices (the data only has price bands). Cited ids are checked against what the tools actually returned.
- **Audit log** (`logs/llm_calls.jsonl`, via `app/logging_utils.py`): one line per model call with model, prompt version, latency, tokens, masked-entity counts and tools used. No question, answer or document text.

See [docs/governance.md](docs/governance.md) for the controls and what production would still need.

## Quick start

Needs Docker Desktop, Python 3.12 or newer (developed on 3.14) and an Anthropic API key. Commands are for PowerShell on Windows.

```powershell
git clone <this-repo-url> biddesk
cd biddesk
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m spacy download en_core_web_lg

python scripts\init_env.py          # creates .env and activepieces.env (random secrets)
# open .env and paste your ANTHROPIC_API_KEY, and set BASEROW_ADMIN_EMAIL / BASEROW_ADMIN_PASSWORD
# (your own choice: setup_baserow.py registers this account as the Baserow admin; it refuses the CHANGE_ME placeholder)

docker compose up -d                # first Baserow start takes several minutes (migrations)
python scripts\check_step1.py       # health check of the stack

python scripts\setup_baserow.py     # creates the BidDesk database, tables, imports past bids
# paste the three BASEROW_* lines it prints into .env

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`data/` (20 RFQ PDFs, 30 past bids, the answer key) is committed; `python scripts\generate_data.py` regenerates it.

### Baserow: create the approval queue view

Open http://localhost:8081, log in with the `BASEROW_ADMIN_EMAIL` / `BASEROW_ADMIN_PASSWORD` from your `.env`, open the `RFQs` table and add a **Grid** view named `Approval queue` with the filter `status` **is** `Awaiting approval`. (Kanban would be nicer but is a paid Baserow feature.)

### Activepieces: import the flow and re-create the connections

1. Open http://localhost:8080 and create the first (local) account.
2. Import [`activepieces/biddesk_flow.json`](activepieces/biddesk_flow.json) as a new flow.
3. Connections are deliberately not exported. Re-create them and re-select them in the two steps that use them:
   - **Baserow**: API URL `http://baserow`, authenticate with the database token from `.env` (or the Baserow login).
   - **SMTP**: host `mailpit`, port `2525`, any dummy user and password, no TLS.
4. In the Create Row step check `table_id` is your `RFQs` table id (`BASEROW_RFQS_TABLE_ID` in `.env`).
5. Publish the flow, copy its webhook URL, put it in `.env` as `MP_WEBHOOK_URL=http://activepieces:80/api/v1/webhooks/<flowId>` and run `docker compose up -d mailpit` so Mailpit calls the flow on every new mail.

If the import does not work in your Activepieces version, rebuild the five steps by hand from the table in the [citizen developer guide](docs/citizen-developer-guide.md).

## Demo walkthrough

```powershell
python scripts\send_rfq.py rfq_01      # one RFQ; or --all for all 20
```

1. **Mailpit** (http://localhost:8025): the RFQ mail with its PDF.
2. **Activepieces** (http://localhost:8080): the flow run, step by step.
3. **Baserow** (`Approval queue` view): a new row with status `Awaiting approval`, extracted fields and `missing_info`.
4. **Mailpit** again: the notification e-mail to the bid manager.
5. Change the row's status to `Approved` and fill `approved_by`; it leaves the queue.
6. Ask the history questions:
   ```powershell
   python scripts\ask_demo.py
   ```
   Five questions: wins by equipment and service, a price question that must not invent exact prices, a "nothing found" case, and two comparisons of real RFQ rows with similar past bids.

### What it looks like

![The BidDesk RFQ intake flow in Activepieces: Catch Webhook, Router, Send HTTP request, Create Row (Baserow), Send Email.](docs/images/flow-overview.png)

*The five-step Activepieces flow.*

![The RFQs table in Baserow, "Approval queue" view: rows filtered on status Awaiting approval.](docs/images/baserow-approval-queue.png)

*The approval queue: a Baserow grid view filtered on status = Awaiting approval.*

![Mailpit inbox: incoming RFQ mails with their PDF attachments, and the notification mails the flow sent to the bid manager.](docs/images/mailpit-inbox.png)

*Mailpit inbox: incoming RFQ mails with their PDF attachments, and the notification mails the flow sent to the bid manager.*

![The notification e-mail: extracted fields and what is missing (here the site).](docs/images/notification-email.png)

*The notification e-mail: extracted fields and what is missing (here the site).*

Output of `python scripts\ask_demo.py` for two of the five questions (questions 2 and 4). Note the agent says only price bands are recorded, and the citations are bid ids the tools actually returned:

```text
==============================================================================
Q2: Which compressor upgrades have we bid on? Give the outcome and the exact EUR price of each.
------------------------------------------------------------------------------
We have bid on three compressor upgrades. The records hold only a price band for each bid, not an
exact price, so I can't give exact EUR prices.

| Bid | Customer | Scope | Price band | Outcome |
|---|---|---|---|---|
| NTS-B-2023-001 | Corvane District Heating | NW-C12 axial air compressor: anti-surge control upgrade and vibration monitoring retrofit | 50–150k EUR | Lost |
| NTS-B-2023-003 | Corvane District Heating | NW-C12 axial air compressor: anti-surge control upgrade and vibration monitoring retrofit | 500k–1M EUR | Lost |
| NTS-B-2025-003 | Piraeus Offshore Services | NW-C12 axial air compressor: re-rate to a new duty point with new impellers | >1M EUR | Lost |

All three were lost.

NTS-B-2023-001 and NTS-B-2023-003 have the same customer and scope but very different price bands.

Cited bid_ids: NTS-B-2023-001, NTS-B-2023-003, NTS-B-2025-003
Tools used:    search_past_bids

==============================================================================
Q4: Summarise RFQ row 3 and show similar past bids.
------------------------------------------------------------------------------
**RFQ row 3**
- **Customer and site:** Brightwater Utilities, Calder Bay.
- **Equipment and service:** compressor, overhaul.
- **Scope:** Full overhaul of an NW-C12 axial air compressor. It includes rotor balancing and
renewal of the bearings and dry gas seal.
- **Outage window:** 04 Feb 2027 to 23 Mar 2027.
- **Due date:** 2027-03-02.
- **Status:** Approved by the Bid Manager.
- **Missing info:** None.

**Similar past bids**
I found no past bids with the same equipment and service (compressor and overhaul). The closest
matches are other compressor bids on the same NW-C12 model, but none is an overhaul:
- **NTS-B-2021-003** (Kestrel Power Partners, 2021): Spare parts for an NW-C12, covering a dry gas
seal cartridge and bearings. Band 50-150k EUR, Won. This is the closest match because the components
overlap with the RFQ's seal and bearing renewal.
- **NTS-B-2023-001** (Corvane District Heating, 2023): NW-C12 anti-surge and vibration monitoring
upgrade. Band 50-150k EUR, Lost. Same model only.
- **NTS-B-2023-003** (Corvane District Heating, 2023): NW-C12 anti-surge and vibration monitoring
upgrade. Band 500k-1M EUR, Lost. Same model only.
- **NTS-B-2025-003** (Piraeus Offshore Services, 2025): NW-C12 re-rate with new impellers. Band >1M
EUR, Lost. Same model only.

Among overhauls on other equipment, **NTS-B-2020-004** (Solvik Petrochemicals, 2020) is a heavy-duty
turbine overhaul that included bearing renewal and rotor balancing. Band 500k-1M EUR, Lost. It is
only a loose match on scope.

Past bids record price bands only, not exact prices.

Cited bid_ids: NTS-B-2021-003, NTS-B-2023-001, NTS-B-2023-003, NTS-B-2025-003, NTS-B-2020-004
Tools used:    get_rfq, search_past_bids, search_past_bids, search_past_bids
```

## Evaluation

`python scripts\eval.py` runs the extraction on the 20 PDFs (masking on) and compares with `data/answer_key.json`. Results from the last run (`claude-haiku-5-5`, prompt `extract-v1`, full report in [docs/eval_results.md](docs/eval_results.md)):

| Field | Score | Detail |
|---|---|---|
| customer | 100% | 20/20 exact |
| site | 100% | 20/20 exact |
| equipment_type | 100% | 20/20 exact |
| service_type | 100% | 20/20 exact |
| due_date | 100% | 20/20 exact |
| missing_info | 100% | per-file F1; micro precision 1.00, recall 1.00 |
| scope_summary | 95% | keyword overlap with answer key |
| **overall** | **99%** | mean of the 7 fields |

35,696 input and 5,388 output tokens for the 20 documents, about $0.006 at list price. These documents are clean, synthetic and generated from the same templates as the answer key, so the numbers show the pipeline works, not how it would score on real-world RFQs.

## Known limitations

- **The approval queue is a filtered Grid, not a Kanban board**, because Kanban is a paid Baserow feature. Approval is a manual status change; `approved_by` is free text and nothing enforces who may approve.
- **Local, throwaway logins and secrets.** The Baserow admin account and the demo credentials are for a laptop only. The FastAPI service has no authentication.
- **The flow does not check `skipped`.** The Router only lets subjects starting with "RFQ" through. A mail with an "RFQ" subject but no PDF would still create an empty row.
- **Mailpit is a test mail server** (no IMAP, nothing is sent outside). A real deployment needs a real mailbox connector.
- **One PDF per mail, text PDFs only**: no scanned documents or OCR.
- **Masking is limited on purpose** to names, e-mail addresses and phone numbers. Addresses, free-text identifiers and anything unusual are not masked.
- **Synthetic data**: accuracy on real documents is untested.
- The flow export was built from the flow definition stored by Activepieces rather than the UI export button; connection ids and test data are stripped.

## Optional extras: Appsmith

Not part of the core stack and not started by default. [Appsmith](https://www.appsmith.com/) (open-source, low-code app builder) is the natural next layer: a small approval app on top of the Baserow `RFQs` table, with a list of pending RFQs and Approve / Reject buttons instead of editing rows in Baserow's grid.

```powershell
docker compose --profile extras up -d appsmith
```

Then open http://localhost:8082 and create the local admin account on the first visit. The image is about 1 GB and the first start takes a few minutes. To stop it: `docker compose --profile extras stop appsmith`.

This repo only provides the container (image pinned in `docker-compose.yml`, data in the `appsmith_stacks` volume). The app itself is built in the Appsmith UI: add a REST API datasource pointing at `http://baserow` (it shares the compose network) with the Baserow database token in an `Authorization: Token ...` header.

## Repository layout

```
app/            FastAPI service: main, extract, agent, masking, llm, baserow, mailpit, schemas, logging_utils
scripts/        init_env, check_step1, generate_data, setup_baserow, send_rfq, eval, ask_demo
activepieces/   biddesk_flow.json (sanitised flow export)
data/           20 RFQ PDFs, past_bids.csv, answer_key.json, allowlist.json (all synthetic)
docs/           citizen-developer-guide.md, governance.md, eval_results.md
docker-compose.yml   Mailpit, Baserow, Activepieces (+ Postgres, Redis)
```
