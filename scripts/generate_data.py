"""Generate all synthetic data for BidDesk (fictional company: Nordwind Turbine Services).

    python scripts/generate_data.py

Writes:
  data/rfqs/rfq_01.pdf ... rfq_20.pdf   20 customer RFQs (3 layouts, some fields missing on purpose)
  data/past_bids.csv                    30 historical bids
  data/answer_key.json                  ground truth for scripts/eval.py

Everything is invented. Customers, sites, people, e-mails and phone numbers are fictional.
Deterministic: the same seed always produces the same files.
"""
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
RFQ_DIR = ROOT / "data" / "rfqs"
SEED = 42

EQUIPMENT_TYPES = [
    "heavy-duty gas turbine",
    "aeroderivative gas turbine",
    "compressor",
    "generator",
    "combustion parts",
]
SERVICE_TYPES = ["inspection", "overhaul", "upgrade", "spare parts"]

# customer -> sites (all fictional)
CUSTOMERS = {
    "Kestrel Power Partners": ["Harbourside Station", "Marlow Fields"],
    "Aurelian Energy": ["Tessin Valley Plant", "Ostrava Ridge"],
    "Brightwater Utilities": ["Brightwater North", "Calder Bay"],
    "Solvik Petrochemicals": ["Solvik Terminal", "Fjordheim Works"],
    "Meridian Gas Transmission": ["Compressor Station 7", "Compressor Station 12"],
    "Halden Steel Works": ["Halden Mill", "Rauma Yard"],
    "Corvane District Heating": ["Corvane CHP", "Eastgate Heat Plant"],
    "Piraeus Offshore Services": ["Platform Alpha", "Platform Delta"],
    "Valtara Cement": ["Valtara Kiln Plant"],
    "Moorfield Renewables": ["Moor Hybrid Plant"],
}

# Fictional generic unit names (no real OEM designations)
FRAMES = {
    "heavy-duty gas turbine": ["NW-45 heavy-duty unit", "NW-60 heavy-duty unit", "NW-80 heavy-duty unit"],
    "aeroderivative gas turbine": ["NW-22 aeroderivative unit", "NW-30 aeroderivative unit"],
    "compressor": ["NW-C6 centrifugal gas compressor", "NW-C12 axial air compressor"],
    "generator": ["NW-G50 air-cooled generator", "NW-G120 hydrogen-cooled generator"],
    "combustion parts": ["NW-45 dry low-emission combustor set", "NW-60 can-annular liner set"],
}

# Scope lookup keyed by (equipment_type, service_type): only plausible pairs exist.
SCOPES = {
    ("heavy-duty gas turbine", "inspection"): [
        "Combustion inspection with fuel nozzle flow testing and liner check.",
        "Hot gas path inspection with borescope survey and written findings report.",
        "Major inspection with rotor lift-out and non-destructive testing of blades.",
    ],
    ("heavy-duty gas turbine", "overhaul"): [
        "Major overhaul: hot gas path blade and vane replacement, bearing renewal and rotor balancing.",
        "Hot gas path overhaul with coating renewal and tip clearance reset.",
    ],
    ("heavy-duty gas turbine", "upgrade"): [
        "Control system upgrade and retrofit of emissions-reduction hardware.",
        "Efficiency upgrade: new compressor blading and improved tip clearances.",
    ],
    ("heavy-duty gas turbine", "spare parts"): [
        "Supply of one set of first-stage nozzles and a set of fuel nozzles.",
        "Supply of first-stage buckets, shroud blocks and a gasket kit for the next planned outage.",
    ],
    ("aeroderivative gas turbine", "inspection"): [
        "Borescope inspection of compressor and turbine sections with written findings report.",
        "Gearbox and accessory drive inspection including oil debris analysis.",
    ],
    ("aeroderivative gas turbine", "overhaul"): [
        "Gas generator exchange and overhaul with performance test run.",
        "Power turbine overhaul with bearing and seal renewal.",
    ],
    ("aeroderivative gas turbine", "upgrade"): [
        "Installation of online monitoring package with vibration and temperature analytics.",
        "Fuel system retrofit for dual-fuel operation.",
    ],
    ("aeroderivative gas turbine", "spare parts"): [
        "Supply of igniters, fuel nozzles and a sensor kit for the gas generator.",
        "Supply of an inlet filter set, start-motor spares and gasket kit.",
    ],
    ("compressor", "inspection"): [
        "Borescope inspection of compressor stages with blade condition report.",
        "Blade wash and inspection of inlet guide vanes and diaphragms.",
    ],
    ("compressor", "overhaul"): [
        "Full compressor overhaul with rotor balancing, bearing and dry gas seal renewal.",
        "Overhaul of the bundle and bearing housing with new labyrinth seals.",
    ],
    ("compressor", "upgrade"): [
        "Re-rate of the compressor to a new duty point with new impellers.",
        "Anti-surge control upgrade and retrofit of vibration monitoring.",
    ],
    ("compressor", "spare parts"): [
        "Supply of a dry gas seal cartridge, tilting-pad bearings and O-ring kit.",
        "Supply of spare impeller, balance piston and coupling elements.",
    ],
    ("generator", "inspection"): [
        "Rotor inspection with retaining ring test and electrical testing of the stator winding.",
        "Borescope and wedge-tightness inspection of the stator without rotor removal.",
    ],
    ("generator", "overhaul"): [
        "Generator rewind and stator core re-insulation with final high-voltage test.",
        "Rotor rewind and bearing overhaul with balancing.",
    ],
    ("generator", "upgrade"): [
        "Excitation system retrofit and cooling upgrade for higher output.",
        "Retrofit of online partial-discharge monitoring.",
    ],
    ("generator", "spare parts"): [
        "Supply of brush gear, slip-ring spares and a set of stator wedges.",
        "Supply of bearing shells, hydrogen seals and a spare temperature sensor kit.",
    ],
    ("combustion parts", "inspection"): [
        "Dimensional and crack inspection of liners and transition pieces with reconditioning recommendation.",
        "Fuel nozzle flow test and combustor casing inspection.",
    ],
    ("combustion parts", "overhaul"): [
        "Refurbishment of combustion liners and transition pieces with new thermal barrier coating.",
        "Full combustor set overhaul including cross-fire tubes and fuel nozzle rebuild.",
    ],
    ("combustion parts", "upgrade"): [
        "Upgrade to low-emission combustor hardware with new fuel nozzles.",
        "Retrofit of improved liner cooling design for extended inspection interval.",
    ],
    ("combustion parts", "spare parts"): [
        "Supply of combustion liners and transition pieces, delivered to site.",
        "Supply of fuel nozzle tips, cross-fire tubes and spark plugs.",
    ],
}

FIRST_NAMES = ["Anselm", "Greta", "Tobias", "Ilse", "Marek", "Linnea", "Piet", "Noor", "Joaquin", "Freya"]
LAST_NAMES = ["Vandermeer", "Holmgren", "Brandt", "Okonkwo", "Lindqvist", "Santoro", "Kovac", "Reinholt", "Duarte", "Falk"]

# Fields an RFQ may leave out. Customer, equipment type and service type are always present.
OPTIONAL_FIELDS = ["due_date", "site", "operating_hours", "serial_number", "outage_window"]

PRICE_BANDS = ["<50k EUR", "50-150k EUR", "150-500k EUR", "500k-1M EUR", ">1M EUR"]


def fmt_date(d: date, style: int) -> str:
    if style == 0:
        return d.strftime("%d %B %Y")
    if style == 1:
        return d.strftime("%Y-%m-%d")
    return d.strftime("%d.%m.%Y")


def build_rfq(rng: random.Random, idx: int, customer: str, site: str, equipment: str, service: str,
              missing: list[str], today: date) -> dict:
    """Return the ground-truth record (what an ideal extraction would return)."""
    due = today + timedelta(days=rng.randint(30, 200))
    frame = rng.choice(FRAMES[equipment])
    scope = rng.choice(SCOPES[(equipment, service)])
    first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
    contact = f"{first} {last}"
    email = f"{first.lower()}.{last.lower()}@{customer.split()[0].lower()}-procurement.example"
    phone = f"+49 30 5550 {rng.randint(1000, 9999)}"
    return {
        "file": f"rfq_{idx:02d}.pdf",
        "customer": customer,
        "site": None if "site" in missing else site,
        "equipment_type": equipment,
        "service_type": service,
        "due_date": None if "due_date" in missing else due.isoformat(),
        "scope_summary": f"{service.capitalize()} of {frame}: {scope}",
        "missing_info": sorted(missing),
        # not scored, only used to render the PDF
        "_frame": frame,
        "_scope": scope,
        "_contact": contact,
        "_email": email,
        "_phone": phone,
        "_site_hidden": site,
        "_due": due,
        "_hours": rng.choice([18000, 24500, 31200, 41800, 52000]),
        "_serial": f"SN-{rng.randint(10000, 99999)}",
        "_window": f"{(due - timedelta(days=rng.randint(20, 60))).strftime('%d %b %Y')} to "
                   f"{(due + timedelta(days=rng.randint(10, 30))).strftime('%d %b %Y')}",
    }


def render_pdf(rec: dict, layout: int, date_style: int) -> None:
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10.5, leading=15)
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=18, alignment=0)
    small = ParagraphStyle("small", parent=body, fontSize=9, textColor=colors.grey)

    site = rec["_site_hidden"]
    hours = rec["_hours"]
    items: list = []
    path = RFQ_DIR / rec["file"]
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm,
                            topMargin=20 * mm, bottomMargin=20 * mm,
                            title=f"Request for Quotation - {rec['customer']}", author=rec["customer"])

    extra_lines = []
    if "operating_hours" not in rec["missing_info"]:
        extra_lines.append(f"Operating hours at last outage: approx. {hours:,} h.")
    if "serial_number" not in rec["missing_info"]:
        extra_lines.append(f"Unit serial number: {rec['_serial']}.")
    if "outage_window" not in rec["missing_info"]:
        extra_lines.append(f"Planned outage window: {rec['_window']}.")
    due_txt = fmt_date(rec["_due"], date_style)

    if layout == 0:  # formal letter
        items += [Paragraph("REQUEST FOR QUOTATION", h1),
                  Paragraph(f"From: {rec['customer']}, Procurement Department", body),
                  Paragraph("To: Nordwind Turbine Services, Bid Desk", body), Spacer(1, 8)]
        loc = f" at our {site}" if site and "site" not in rec["missing_info"] else ""
        items.append(Paragraph(
            f"Dear Sir or Madam,<br/><br/>We kindly request a quotation for {rec['service_type']} work on a "
            f"{rec['_frame']} ({rec['equipment_type']}){loc}.", body))
        items += [Spacer(1, 6), Paragraph(f"<b>Scope of work.</b> {rec['_scope']}", body)]
        for line in extra_lines:
            items.append(Paragraph(line, body))
        if "due_date" not in rec["missing_info"]:
            items.append(Paragraph(f"Please submit your quotation by <b>{due_txt}</b>.", body))
        items += [Spacer(1, 14),
                  Paragraph(f"Kind regards,<br/>{rec['_contact']}<br/>Senior Buyer, {rec['customer']}<br/>"
                            f"Tel: {rec['_phone']}<br/>E-mail: {rec['_email']}", body)]
    elif layout == 1:  # form / table
        items += [Paragraph(f"{rec['customer']} - Quotation Request Form", h1), Spacer(1, 6)]
        rows = [["Customer", rec["customer"]]]
        if "site" not in rec["missing_info"]:
            rows.append(["Site", site])
        rows += [["Equipment", f"{rec['_frame']} - category: {rec['equipment_type']}"],
                 ["Service required", rec["service_type"]]]
        if "due_date" not in rec["missing_info"]:
            rows.append(["Quote due", due_txt])
        if "operating_hours" not in rec["missing_info"]:
            rows.append(["Operating hours", f"{hours:,} h"])
        if "serial_number" not in rec["missing_info"]:
            rows.append(["Serial no.", rec["_serial"]])
        if "outage_window" not in rec["missing_info"]:
            rows.append(["Outage window", rec["_window"]])
        rows += [["Contact", f"{rec['_contact']}, {rec['_phone']}, {rec['_email']}"]]
        t = Table(rows, colWidths=[40 * mm, 125 * mm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                               ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTSIZE", (0, 0), (-1, -1), 10)]))
        items += [t, Spacer(1, 10), Paragraph(f"<b>Description of work:</b> {rec['_scope']}", body)]
    else:  # short informal e-mail style
        items += [Paragraph("Subject: need a price", h1),
                  Paragraph(f"From: {rec['_contact']} &lt;{rec['_email']}&gt;", small), Spacer(1, 8)]
        loc = f" at {site}" if site and "site" not in rec["missing_info"] else ""
        txt = (f"Hi team, this is {rec['_contact']} from {rec['customer']}. We need {rec['service_type']} "
               f"for our {rec['_frame']}{loc} ({rec['equipment_type']}). {rec['_scope']} ")
        txt += " ".join(extra_lines) + " "
        if "due_date" not in rec["missing_info"]:
            txt += f"We need your offer before {due_txt}. "
        txt += f"Call me on {rec['_phone']} if anything is unclear. Thanks, {rec['_contact'].split()[0]}"
        items.append(Paragraph(txt, body))
    items += [Spacer(1, 18), Paragraph("Synthetic document for a personal learning project. Not a real request.", small)]
    doc.build(items)


def make_rfqs() -> None:
    rng = random.Random(SEED)
    RFQ_DIR.mkdir(parents=True, exist_ok=True)
    today = date(2026, 11, 5)
    customers = list(CUSTOMERS)
    key = []
    # fixed missing-info plan: 6 complete, the rest drop 1-3 optional fields
    for i in range(1, 21):
        customer = customers[(i - 1) % len(customers)] if i <= 10 else rng.choice(customers)
        site = rng.choice(CUSTOMERS[customer])
        equipment = EQUIPMENT_TYPES[(i - 1) % len(EQUIPMENT_TYPES)]
        service = SERVICE_TYPES[(i * 3 + i // 5) % len(SERVICE_TYPES)]
        n_missing = 0 if i % 3 == 0 and i <= 18 else rng.randint(1, 3)
        missing = rng.sample(OPTIONAL_FIELDS, n_missing)
        rec = build_rfq(rng, i, customer, site, equipment, service, missing, today)
        render_pdf(rec, layout=i % 3, date_style=rng.randint(0, 2))
        key.append({k: v for k, v in rec.items() if not k.startswith("_")})
    (ROOT / "data" / "answer_key.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
    print(f"Wrote {len(key)} PDFs to {RFQ_DIR} and data/answer_key.json")


# Price-band weights per service, over PRICE_BANDS (<50k, 50-150k, 150-500k, 500k-1M, >1M)
BAND_WEIGHTS = {
    "spare parts": [35, 40, 20, 5, 0],
    "inspection": [30, 45, 20, 5, 0],
    "upgrade": [0, 10, 35, 35, 20],
    "overhaul": [0, 5, 30, 40, 25],
}


def make_past_bids() -> None:
    rng = random.Random(SEED + 1)
    n = 30
    outcomes = ["Won"] * 12 + ["Lost"] * 12 + ["No bid"] * 6  # 40 / 40 / 20 %
    rng.shuffle(outcomes)
    rows = []
    counters: dict[int, int] = {}
    customers = list(CUSTOMERS)
    for i in range(n):
        year = rng.randint(2020, 2025)
        counters[year] = counters.get(year, 0) + 1
        equipment = EQUIPMENT_TYPES[i % len(EQUIPMENT_TYPES)]
        service = rng.choice(SERVICE_TYPES)
        scope = f"{rng.choice(FRAMES[equipment])}: {rng.choice(SCOPES[(equipment, service)])}"
        rows.append({
            "bid_id": f"NTS-B-{year}-{counters[year]:03d}",
            "customer": rng.choice(customers),
            "equipment_type": equipment,
            "service_type": service,
            "scope": scope,
            "price_band": rng.choices(PRICE_BANDS, weights=BAND_WEIGHTS[service])[0],
            "year": year,
            "outcome": outcomes[i],
        })
    rows.sort(key=lambda r: r["bid_id"])
    path = ROOT / "data" / "past_bids.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows to {path}")


def make_allowlist() -> None:
    """Master data the PII masker must NOT treat as personal names (customers, sites, unit names)."""
    allow = {
        "companies": ["Nordwind Turbine Services", "Nordwind"] + list(CUSTOMERS),
        "sites": sorted({s for sites in CUSTOMERS.values() for s in sites}),
        "units": sorted({f for frames in FRAMES.values() for f in frames}),
    }
    (ROOT / "data" / "allowlist.json").write_text(json.dumps(allow, indent=2), encoding="utf-8")
    print("Wrote data/allowlist.json")


if __name__ == "__main__":
    make_rfqs()
    make_past_bids()
    make_allowlist()
