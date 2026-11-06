# Build your own intake flow from the BidDesk template

> Personal self-learning project. Not affiliated with any employer. All data is synthetic.

For people who do not write code. You will take the BidDesk RFQ flow, point it at your own mail rule and your own table, test it and publish it. You need the stack from the [README quick start](../README.md) running (Mailpit, Baserow, Activepieces and the extraction service).

## The flow at a glance

| # | Step (Activepieces) | What it does | What you may change |
|---|---|---|---|
| 1 | **Catch Webhook** (trigger) | Mailpit calls it for every new mail | Nothing; copy its published URL into `MP_WEBHOOK_URL` once |
| 2 | **Router** | Continues only if the mail subject **starts with** `RFQ` (not case sensitive) | The field, operator and text of the condition |
| 3 | **Send HTTP request** | `POST http://host.docker.internal:8000/extract` with body `{"message_id": <the mail's ID>}` | The URL if the service runs elsewhere. Not the body key |
| 4 | **Create Row** (Baserow) | Writes the extracted fields to a table, status `Awaiting approval` | Table and field mapping |
| 5 | **Send Email** (SMTP) | Notifies the bid manager | Recipient, subject, text |

## 1. Import the template

1. Open Activepieces at http://localhost:8080.
2. Create a new flow and choose the import option, then pick `activepieces/biddesk_flow.json`.
3. Rename the flow to your own name.

If import is not offered or fails, create the five steps yourself using the table above; every setting is listed there and in the steps below.

## 2. Create the two connections

Connections are never exported with a template, so make them yourself.

- **Baserow**: API URL `http://baserow` (not `localhost`; the flow runs inside Docker). Authenticate with a database token (Baserow: account menu > My settings > Database tokens) or with your Baserow login.
- **SMTP**: host `mailpit`, port `2525`, any user name and password, no TLS. Port 2525 matters (see troubleshooting).

Then open the **Create Row** step and the **Send Email** step and select your connection in each one.

## 3. Change the Router condition

Open the **Router** step, branch 1. The condition reads: `Subject` **starts with** `RFQ`. Change the text to your own subject convention, for example `Quote request`. Keep it a prefix that your own notification e-mail does **not** start with (see "loop guard" below). The *Otherwise* branch stays empty: those mails are ignored.

## 4. Point it at your own Baserow table

1. Create the table in Baserow with matching field types: text for names, a single select for status and categories, a **date with time** for dates, long text for summaries.
2. In **Create Row**, choose your database and table, then map each field. Click into a field and use the **Data Selector** to pick values from step 3's output (for example `customer`, `site`, `due_date`, `missing_info_text`).
3. Set `status` to a fixed value such as `Awaiting approval`.
4. In Baserow add a Grid view with a filter on `status` = `Awaiting approval`. That is your approval queue.

If you need new fields from the AI step, they must be added to the extraction service (a developer task); the flow only maps what `/extract` returns.

## 5. Test

1. In each step use **Test step** from the top: the webhook first (send a sample with `python scripts\send_rfq.py rfq_01` while the flow listens), then the HTTP step, then Create Row, then Send Email.
2. Check that a row appeared in your table, and the notification arrived in Mailpit (http://localhost:8025).

## 6. Publish and connect Mailpit

1. **Publish** the flow. Test runs use a different webhook address (ending in `/test`) than the published flow.
2. Copy the **published** webhook URL, put it in `.env` as `MP_WEBHOOK_URL=http://activepieces:80/api/v1/webhooks/<flowId>` (no `/test`), and run `docker compose up -d mailpit`.
3. Send another RFQ and watch the **Runs** list.

## Troubleshooting (problems we actually hit)

**The HTTP step fails with `Mailpit: 404 (message_id='{{trigger.body.ID}}')`**
The value was typed by hand, so the flow sent the literal text instead of the mail id. Delete it and insert the value with the **Data Selector** (click the field, pick `ID` from the trigger's output). The key is `ID` in capitals.

**The notification e-mail never sends, or SMTP times out / is refused**
Use port **2525**, host `mailpit`. The Activepieces SMTP step only allows ports 25, 465, 587 and 2525, and Mailpit listens on 2525 inside Docker. Port 1025 only works from your Windows machine.

**The flow runs again and again (a loop)**
Your own notification e-mail is also a new mail, so Mailpit fires the webhook for it too. The Router stops it because the subject starts with `[BidDesk]`, not `RFQ`. Never give the notification a subject that matches the Router condition.

**"Invalid ... or API URL" when saving the Baserow connection, or a 404 with `{"error":true,...,"message":"Server Error"}`**
Baserow only serves its API for host names it was told about. The compose file sets `BASEROW_EXTRA_PUBLIC_URLS=http://baserow,http://host.docker.internal:8081`; if you changed or removed it, restore it and recreate the Baserow container (`docker compose up -d baserow`). Use API URL `http://baserow`.

**Only the first missing item shows up in Baserow**
Map `missing_info_text` (all items, comma separated), not `missing_info` (a list, where the mapping picks the first element).

**The date does not save**
The Baserow field must be a date **with time**; the flow's date mapping is date-time.

**The HTTP step cannot reach the extraction service**
Start it with `--host 0.0.0.0` (`uvicorn app.main:app --host 0.0.0.0 --port 8000`) and allow it through the Windows firewall prompt. The flow reaches your PC as `host.docker.internal`.

**Nothing happens when a mail arrives**
`MP_WEBHOOK_URL` is empty, still has the `/test` ending, or the flow is not published. Fix `.env`, then `docker compose up -d mailpit`.
