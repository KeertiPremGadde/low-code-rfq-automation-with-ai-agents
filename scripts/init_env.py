"""Create .env and activepieces.env from the templates (stdlib only).

Run once from the project root:  python scripts/init_env.py
Existing files are never overwritten.
"""
import secrets
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def make_env() -> None:
    target = ROOT / ".env"
    if target.exists():
        print(".env already exists - left unchanged")
        return
    shutil.copy(ROOT / ".env.example", target)
    print("Created .env  -> open it and paste your ANTHROPIC_API_KEY")


def make_activepieces_env() -> None:
    target = ROOT / "activepieces.env"
    if target.exists():
        print("activepieces.env already exists - left unchanged")
        return
    text = (ROOT / "activepieces.env.example").read_text(encoding="utf-8")
    text = (
        text.replace("__RANDOM_HEX_64__", secrets.token_hex(64))
        .replace("__RANDOM_HEX_32__", secrets.token_hex(32))
        .replace("__RANDOM_HEX_16__", secrets.token_hex(16))  # 32 hex chars
        .replace("__DB_PASSWORD__", secrets.token_hex(24))
    )
    target.write_text(text, encoding="utf-8", newline="\n")
    print("Created activepieces.env with random secrets")


if __name__ == "__main__":
    make_env()
    make_activepieces_env()
