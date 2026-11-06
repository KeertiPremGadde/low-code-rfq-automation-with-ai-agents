"""Send synthetic RFQ e-mails to Mailpit over SMTP (localhost:1025).

    python scripts/send_rfq.py --test            plain mail, no attachment
    python scripts/send_rfq.py rfq_01            one RFQ (name or number)
    python scripts/send_rfq.py --all             all 20, with a short pause between
"""
import argparse
import json
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RFQ_DIR = ROOT / "data" / "rfqs"
KEY = ROOT / "data" / "answer_key.json"
SMTP_HOST, SMTP_PORT = "localhost", 1025


def send(msg: EmailMessage) -> None:
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
        s.send_message(msg)


def send_test() -> None:
    msg = EmailMessage()
    msg["From"] = "someone@example.com"
    msg["To"] = "bids@nordwind-turbine.example"
    msg["Subject"] = "Hello (plain test mail, no RFQ)"
    msg.set_content("Plain test mail with no attachment. BidDesk should ignore this.")
    send(msg)
    print("Sent plain test mail")


def send_rfq(entry: dict) -> None:
    pdf = RFQ_DIR / entry["file"]
    if not pdf.exists():
        raise SystemExit(f"{pdf} not found - run scripts/generate_data.py first")
    msg = EmailMessage()
    msg["From"] = f"procurement@{entry['customer'].split()[0].lower()}-procurement.example"
    msg["To"] = "bids@nordwind-turbine.example"
    msg["Subject"] = f"RFQ - {entry['customer']} - {entry['equipment_type']}"
    msg.set_content(f"Please find our request for quotation attached.\n\n{entry['customer']}")
    msg.add_attachment(pdf.read_bytes(), maintype="application", subtype="pdf", filename=entry["file"])
    send(msg)
    print(f"Sent {entry['file']}: {msg['Subject']}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("which", nargs="?", help="rfq_01, 01 or 1")
    p.add_argument("--all", action="store_true")
    p.add_argument("--test", action="store_true")
    p.add_argument("--delay", type=float, default=2.0, help="seconds between mails with --all")
    a = p.parse_args()

    if a.test:
        return send_test()
    key = json.loads(KEY.read_text(encoding="utf-8"))
    if a.all:
        for e in key:
            send_rfq(e)
            time.sleep(a.delay)
        return
    if not a.which:
        p.error("give an RFQ (e.g. rfq_01), --all or --test")
    num = int(a.which.lower().replace("rfq_", "").replace(".pdf", ""))
    send_rfq(next(e for e in key if e["file"] == f"rfq_{num:02d}.pdf"))


if __name__ == "__main__":
    main()
