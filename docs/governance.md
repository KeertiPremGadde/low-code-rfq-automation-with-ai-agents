# Governance notes

> Personal self-learning project. Not affiliated with any employer. All data is synthetic.

What BidDesk does today to keep an AI step under control, where it falls short, and what a production version would need. It is a demo on a laptop; treat the last section as the real to-do list.

## Controls in place

### PII masking before the model

Text extracted from an RFQ PDF is passed through Presidio (`app/masking.py`) before it is sent to the model. Only three entity types are masked: `PERSON`, `EMAIL_ADDRESS` and `PHONE_NUMBER`; they are replaced with placeholders such as `<PERSON>`. The `/ask` question is masked the same way.

Things found while testing, now handled:
- Presidio's built-in e-mail recognizer ignores addresses on reserved or internal domains, so an extra any-domain pattern is registered.
- Serial numbers such as `SN-65302` were detected as names; a name hit that contains a digit is dropped.
- Phone numbers wrapped across a PDF line break were missed; an extra pattern covers them.

The evaluation script checks masking on every document (each synthetic RFQ has exactly one e-mail and one phone number) and reports damaged or missed entities. The last run: 0 issues.

### Allow-list

Customer, site, company and equipment-unit names are loaded from `data/allowlist.json`. A `PERSON` hit that overlaps one of these names is discarded, so "Kestrel Power Partners" is not masked as a person. In a real system this list would be fed from master data (customer master, site register).

### Human approval

The AI step never decides. Every extracted RFQ becomes a row with status `Awaiting approval`; a person reviews it in the Approval queue and changes it to `Approved` or `Rejected`, filling in `approved_by`. The row also shows `missing_info`, so reviewers see what the AI could not find instead of a guess. The extraction prompt forbids guessing: unknown fields are null and listed in `missing_info`.

Limitation: the approval is a convention. Baserow does not stop a user from editing `status` without filling in `approved_by`.

### Logging without personal data

`logs/llm_calls.jsonl` gets one line per model call: timestamp, model, prompt version, latency, input and output tokens, counts of masked entities, and for `/ask` the tool names used, a request id and how many cited bid ids were verified. It never contains document text, questions, answers, tool results or masked values. The file is git-ignored.

### Model and prompt versioning

The model ids and the prompt version come from `.env` (`LLM_EXTRACT_MODEL`, `LLM_AGENT_MODEL`, `PROMPT_VERSION`, `AGENT_PROMPT_VERSION`). Each extracted RFQ row stores the `model` and `prompt_version` that produced it, and every log line carries them. After changing either, re-run `python scripts\eval.py` and compare with `docs/eval_results.md`; the answer key and per-field scoring make a regression visible.

### Grounded answers

`/ask` may only answer from tool results, must cite `bid_id`s and must say when nothing was found. The service checks the cited ids: only ids that were actually returned by a tool in that request are reported as citations; others are dropped and counted in the log. The data holds price bands only, so the agent is told never to invent prices.

### Prompt-injection posture

Document text and tool results are wrapped or described as data in the prompts, and the model is told not to follow instructions found in them. This lowers the risk; it does not remove it.

## Data-protection questions this design answers

A data-loss-prevention review asks a few standard questions. These are the answers for this project:

| DLP question | In BidDesk |
|---|---|
| Which systems may exchange data? | Only the flow, the extraction service and the tables talk to each other; the one external call is to the model API |
| What sensitive information must not leave? | Names, e-mail addresses, phone numbers: masked before the model call |
| What is allowed through despite looking sensitive? | The allow-list of customer, site and unit names |
| Who can see what happened? | The audit log, without the sensitive values |

## What production would need

- **Real authentication and authorization.** The FastAPI service is open on the local network. Put it behind authenticated access (for example API keys or OAuth), and restrict who can call `/extract` and `/ask`.
- **Secrets management.** Replace `.env` files with a secrets manager; rotate the model API key and the Baserow token; no default passwords.
- **Role-based access.** Separate roles for requesters, approvers and administrators. Enforce who may set `Approved` and record the approver automatically from the signed-in user, rather than free text.
- **Retention and deletion.** Decide how long RFQ mails, PDFs, extracted rows and logs are kept and delete them on schedule. Define what happens on a deletion request.
- **Stronger PII handling.** Cover more entity types (addresses, identifiers), evaluate masking on real documents, and review what the model provider retains under the account's data terms.
- **A real mailbox connector** instead of the test mail server, with delivery failures and retries handled.
- **Operational monitoring.** Alerts on failed runs, model errors and cost; a dead-letter path for mails that fail extraction (today a mail with no PDF but an "RFQ" subject still creates an empty row).
- **Evaluation on real data** with a human-reviewed sample, tracked over time, before any change of model or prompt goes live.
- **Change control** for the flow itself: versioned exports, review before publishing, a test environment.
