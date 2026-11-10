# Setup

Needs Docker Desktop, Python 3.12 or newer and an Anthropic API key. Commands are for PowerShell on Windows.

```powershell
git clone https://github.com/KeertiPremGadde/low-code-rfq-automation-with-ai-agents.git biddesk
cd biddesk
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m spacy download en_core_web_lg

python scripts\init_env.py          # creates .env and activepieces.env (random secrets)
# in .env: add ANTHROPIC_API_KEY and choose BASEROW_ADMIN_EMAIL / BASEROW_ADMIN_PASSWORD
# (setup_baserow.py creates this Baserow admin account)

docker compose up -d                # first Baserow start takes several minutes (migrations)
python scripts\check_stack.py       # health check of the stack

python scripts\setup_baserow.py     # creates the BidDesk database, tables, imports past bids
# paste the three BASEROW_* lines it prints into .env

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`data/` (20 RFQ PDFs, 30 past bids, the answer key) is committed; `python scripts\generate_data.py` regenerates it.

### Baserow: create the approval queue view

Open http://localhost:8081, log in with the `BASEROW_ADMIN_EMAIL` / `BASEROW_ADMIN_PASSWORD` from your `.env`, open the `RFQs` table and add a **Grid** view named `Approval queue` with the filter `status` **is** `Awaiting approval`. (Kanban would be nicer but is a paid Baserow feature.)

### Activepieces: import the flow and re-create the connections

1. Open http://localhost:8080 and create the first (local) account.
2. Import [`activepieces/biddesk_flow.json`](../activepieces/biddesk_flow.json) as a new flow.
3. Connections are not part of the export (it was built from the flow definition stored by Activepieces, with connection ids and test data removed). Re-create them and re-select them in the two steps that use them:
   - **Baserow**: API URL `http://baserow`, authenticate with the database token from `.env` (or the Baserow login).
   - **SMTP**: host `mailpit`, port `2525`, any dummy user and password, no TLS.
4. In the Create Row step check `table_id` is your `RFQs` table id (`BASEROW_RFQS_TABLE_ID` in `.env`).
5. Publish the flow, copy its webhook URL, put it in `.env` as `MP_WEBHOOK_URL=http://activepieces:80/api/v1/webhooks/<flowId>` and run `docker compose up -d mailpit` so Mailpit calls the flow on every new mail.

If the import does not work in your Activepieces version, rebuild the five steps by hand from the table in the [citizen developer guide](citizen-developer-guide.md).

## Optional: Appsmith

Not part of the core stack and not started by default. [Appsmith](https://www.appsmith.com/) (open-source, low-code app builder) is the natural next layer: a small approval app on top of the Baserow `RFQs` table, with a list of pending RFQs and Approve / Reject buttons instead of editing rows in Baserow's grid.

```powershell
docker compose --profile extras up -d appsmith
```

Then open http://localhost:8082 and create the local admin account on the first visit. The image is about 1 GB and the first start takes a few minutes. To stop it: `docker compose --profile extras stop appsmith`.

This repo only provides the container (image pinned in `docker-compose.yml`, data in the `appsmith_stacks` volume). The app itself is built in the Appsmith UI: add a REST API datasource pointing at `http://baserow` (it shares the compose network) with the Baserow database token in an `Authorization: Token ...` header.
