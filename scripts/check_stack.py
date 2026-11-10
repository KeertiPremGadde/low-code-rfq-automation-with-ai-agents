"""Health check of the local stack (stdlib only, run from the project root).

    python scripts/check_stack.py

Checks:
  1. Mailpit UI/API, Baserow and Activepieces answer on localhost.
  2. A test email sent over SMTP (port 1025) shows up in Mailpit.
  3. From inside the Activepieces container: Baserow (http://baserow), Mailpit
     (http://mailpit:8025) and your Windows host (http://host.docker.internal:8000)
     are reachable. A throwaway web server is started on port 8000 for this test.
"""
import http.server
import json
import smtplib
import subprocess
import threading
import time
import urllib.request
from email.message import EmailMessage

OK, FAIL = "PASS", "FAIL"
results = []


def record(name, passed, detail=""):
    results.append(passed)
    print(f"[{OK if passed else FAIL}] {name}" + (f"  ({detail})" if detail else ""))


def http_get(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read()


# 1. Services on localhost --------------------------------------------------
for name, url in [
    ("Mailpit API  localhost:8025", "http://localhost:8025/api/v1/info"),
    ("Baserow      localhost:8081", "http://localhost:8081/api/settings/"),
    ("Activepieces localhost:8080", "http://localhost:8080/api/v1/flags"),
]:
    try:
        status, _ = http_get(url)
        record(name, status == 200, f"HTTP {status}")
    except Exception as e:  # noqa: BLE001
        record(name, False, str(e))

# 2. SMTP -> Mailpit ------------------------------------------------------------
subject = f"BidDesk stack check {int(time.time())}"
try:
    msg = EmailMessage()
    msg["From"] = "rfq-test@example.com"
    msg["To"] = "bids@nordwind-turbine.example"
    msg["Subject"] = subject
    msg.set_content("SMTP test from check_stack.py. Synthetic data.")
    with smtplib.SMTP("localhost", 1025, timeout=10) as s:
        s.send_message(msg)
    time.sleep(1)
    _, body = http_get("http://localhost:8025/api/v1/messages?limit=20")
    found = any(m.get("Subject") == subject for m in json.loads(body).get("messages", []))
    record("SMTP 1025 -> Mailpit inbox", found)
except Exception as e:  # noqa: BLE001
    record("SMTP 1025 -> Mailpit inbox", False, str(e))

# 3. Container-to-container and container-to-host --------------------------------
class Hello(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"hello from windows")

    def log_message(self, *args):
        pass


server = None
try:
    server = http.server.ThreadingHTTPServer(("0.0.0.0", 8000), Hello)
    threading.Thread(target=server.serve_forever, daemon=True).start()
except OSError as e:
    print(f"(port 8000 busy, skipping host test: {e})")

NODE = (
    "const u=process.argv[1];"
    "fetch(u,{signal:AbortSignal.timeout(8000)})"
    ".then(r=>{console.log(r.status);process.exit(r.status<500?0:1)})"
    ".catch(e=>{console.log(e.message);process.exit(1)})"
)
targets = [
    ("Activepieces -> Baserow  http://baserow", "http://baserow/api/settings/"),
    ("Activepieces -> Mailpit  http://mailpit:8025", "http://mailpit:8025/api/v1/info"),
]
if server:
    targets.append(("Activepieces -> Windows host:8000", "http://host.docker.internal:8000/"))

for name, url in targets:
    try:
        p = subprocess.run(
            ["docker", "exec", "biddesk-activepieces", "node", "-e", NODE, url],
            capture_output=True, text=True, timeout=30,
        )
        out = (p.stdout or p.stderr).strip()
        record(name, p.returncode == 0, out)
    except Exception as e:  # noqa: BLE001
        record(name, False, str(e))

if server:
    server.shutdown()

print()
print(f"{sum(results)}/{len(results)} checks passed")
if not all(results):
    print("Paste the output above into the chat and I'll help fix it.")
