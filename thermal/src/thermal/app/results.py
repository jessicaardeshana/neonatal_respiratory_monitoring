"""Results and limits page data, read from the real report files so numbers cannot drift from the code."""

from __future__ import annotations

from pathlib import Path

FIGURES = Path(__file__).resolve().parents[3] / "figures"

REPORTS = {
    "demo": "demo_report.md",
    "rate": "phase3_report.md",
    "apnea": "phase4_report.md",
    "incubator": "phase4b_report.md",
}

# Shown on the Results page and never hidden (DEMO_APP_SPEC.md Section 9).
LIMITS = [
    {"title": "Everything here is simulated", "body": "All numbers come from a physics-based model, not a camera. No hardware recordings exist yet."},
    {"title": "20 s pauses are borderline", "body": "The detector catches roughly 87-93% of 20 s pauses, because a 20 s pause sits right on its 20 s minimum. Loosening the rule catches more but also flags shorter pauses."},
    {"title": "Warm incubators hurt apnea detection first", "body": "Rate estimation holds up to about 33 degC, but pause detection degrades from about 28 degC when the head moves a little (about 33 degC if it is perfectly still). Head motion is the biggest factor."},
    {"title": "A face leaving the view looks like apnea", "body": "Good breathing followed by nothing is indistinguishable from a real pause without extra information such as face tracking."},
    {"title": "The camera path is unverified", "body": "The Lepton frame format, units, USB identity and timing are all from memory. The live mode has never run on a real device."},
    {"title": "Not modeled", "body": "Incubator canopy material (many plastics block long-wave infrared), humidity and condensation, and camera distance."},
    {"title": "Timing is optimistic", "body": "The pipeline uses a zero-phase filter that looks slightly into the future. A fully real-time version has not been evaluated."},
    {"title": "Proof of concept, not a medical device", "body": "Nothing here is clinically validated. No patient or infant data has been used."},
]


def parse_md_tables(text: str) -> list[dict]:
    """Every markdown pipe table in ``text`` -> {"header": [...], "rows": [[...], ...]}."""
    tables, cur = [], None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if cur is None:
                cur = {"header": cells, "rows": []}
            else:
                cur["rows"].append(cells)
        elif cur is not None:
            tables.append(cur)
            cur = None
    if cur is not None:
        tables.append(cur)
    return tables


def load_results(figures_dir: Path = FIGURES) -> dict:
    reports = {}
    for key, name in REPORTS.items():
        path = figures_dir / name
        if path.exists():
            text = path.read_text()
            reports[key] = {"file": name, "markdown": text, "tables": parse_md_tables(text)}
    return {"reports": reports, "limits": LIMITS,
            "disclaimer": "All figures are from a simulation model, not measurements. Proof of concept, not a medical device."}
