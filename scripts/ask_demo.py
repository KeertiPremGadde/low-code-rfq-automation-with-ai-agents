"""Ask the /ask agent five questions that exercise both tools.

    python scripts/ask_demo.py            (the API must be running: uvicorn app.main:app --port 8000)

Questions 4 and 5 use real RFQ row ids from your Baserow RFQs table (run the flow first so rows exist).
"""
import sys
import textwrap
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.baserow import list_rfq_ids  # noqa: E402

API = "http://localhost:8000"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # model answers may contain dashes etc.


def main() -> None:
    ids = list_rfq_ids()
    if not ids:
        sys.exit("The RFQs table is empty - send an RFQ through the flow first (python scripts\\send_rfq.py rfq_01).")
    first, last = ids[0], ids[-1]
    questions = [
        # search_past_bids
        "Which past aeroderivative gas turbine overhauls did we win, and what was the price band?",
        # search_past_bids + must not invent prices
        "Which compressor upgrades have we bid on? Give the outcome and the exact EUR price of each.",
        # nothing found -> must say so
        "Did we ever win a compressor overhaul?",
        # get_rfq + search_past_bids
        f"Summarise RFQ row {first} and show similar past bids.",
        # get_rfq + search_past_bids
        f"For RFQ row {last}, compare it with our past bids of the same equipment and service type: "
        "typical price band and how often we won?",
    ]
    with httpx.Client(timeout=180) as c:
        for i, q in enumerate(questions, 1):
            print(f"\n{'=' * 78}\nQ{i}: {q}\n{'-' * 78}")
            r = c.post(f"{API}/ask", json={"question": q})
            if r.status_code != 200:
                print(f"ERROR {r.status_code}: {r.text[:300]}")
                continue
            d = r.json()
            for line in d["answer"].splitlines():
                wrap = line.strip() and not line.lstrip().startswith("|")  # keep table rows on one line
                print(textwrap.fill(line, 100) if wrap else line)
            print(f"\nCited bid_ids: {', '.join(d['cited_bid_ids']) or '(none)'}")
            print(f"Tools used:    {', '.join(d['tools_used']) or '(none)'}")


if __name__ == "__main__":
    main()
