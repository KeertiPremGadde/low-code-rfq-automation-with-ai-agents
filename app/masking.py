"""PII masking with Presidio. Only PERSON, EMAIL_ADDRESS and PHONE_NUMBER are masked.

The AnalyzerEngine (spaCy en_core_web_lg) is heavy, so it is created once at startup.
Customer, site, company and unit names come from data/allowlist.json (the "master data"):
a PERSON hit that overlaps one of those names is dropped, so "Kestrel Power Partners"
is not masked as a person.
"""
import json
import logging
import re
from collections import Counter
from pathlib import Path

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer

log = logging.getLogger("biddesk.masking")
ROOT = Path(__file__).resolve().parent.parent
ENTITIES = ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"]


def load_allowlist(path: Path = ROOT / "data" / "allowlist.json") -> list[str]:
    if not path.exists():
        log.warning("allow-list %s not found - names will not be protected", path)
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return sorted({t for terms in data.values() for t in terms}, key=len, reverse=True)


class Masker:
    def __init__(self) -> None:
        self.analyzer = AnalyzerEngine()  # loads en_core_web_lg once
        # Presidio's built-in e-mail recognizer validates the TLD, so it misses synthetic
        # addresses on the reserved ".example" domain (and any internal domain). Add a plain pattern.
        self.analyzer.registry.add_recognizer(PatternRecognizer(
            supported_entity="EMAIL_ADDRESS", name="AnyTldEmailRecognizer",
            patterns=[Pattern("email_any_tld", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", 0.95)]))
        # International numbers that PDF text extraction wrapped across a line break.
        self.analyzer.registry.add_recognizer(PatternRecognizer(
            supported_entity="PHONE_NUMBER", name="WrappedIntlPhoneRecognizer",
            patterns=[Pattern("intl_phone_wrapped", r"\+\d{1,3}(?:[ \t\r\n]+\d{2,5}){2,4}", 0.8)]))
        terms = load_allowlist()
        self.allow_re = re.compile("|".join(re.escape(t) for t in terms), re.I) if terms else None

    def mask(self, text: str) -> tuple[str, dict[str, int]]:
        """Return (masked_text, {entity_type: count}). Placeholders look like <PERSON>."""
        found = self.analyzer.analyze(text=text, language="en", entities=ENTITIES)
        allow_spans = [m.span() for m in self.allow_re.finditer(text)] if self.allow_re else []
        keep = []
        for r in found:
            if r.entity_type == "PERSON" and any(r.start < e and r.end > s for s, e in allow_spans):
                continue  # known company/site/unit name, not a person
            if r.entity_type == "PERSON" and any(ch.isdigit() for ch in text[r.start:r.end]):
                continue  # names contain no digits: serial numbers like SN-65302 are not people
            keep.append(r)
        # resolve overlaps: highest score first, skip anything overlapping an accepted span
        accepted: list = []
        for r in sorted(keep, key=lambda r: (-r.score, r.start)):
            if all(r.end <= a.start or r.start >= a.end for a in accepted):
                accepted.append(r)
        out = text
        for r in sorted(accepted, key=lambda r: r.start, reverse=True):
            out = out[: r.start] + f"<{r.entity_type}>" + out[r.end:]
        return out, dict(Counter(r.entity_type for r in accepted))


_masker: Masker | None = None


def get_masker() -> Masker:
    global _masker
    if _masker is None:
        _masker = Masker()
    return _masker
