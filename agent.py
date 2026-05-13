"""
Autonomous Insurance Claims Processing Agent
Uses Google Gemini AI (FREE) to extract, validate, and route FNOL claims
"""

import os
import json
import glob
import sys
import pdfplumber
from pypdf import PdfReader
from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# ─────────────────────────────────────────────
# 1. PDF / TXT TEXT EXTRACTION
# ─────────────────────────────────────────────

def extract_text(file_path: str) -> str:
    """Extract text from PDF or TXT file."""
    if file_path.endswith(".txt"):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip()

    text = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception:
        reader = PdfReader(file_path)
        for page in reader.pages:
            text += (page.extract_text() or "") + "\n"

    return text.strip()


# ─────────────────────────────────────────────
# 2. AI FIELD EXTRACTION VIA GEMINI
# ─────────────────────────────────────────────

EXTRACTION_PROMPT = """
You are an expert insurance claims analyst. Extract ALL available fields from the FNOL (First Notice of Loss) document text below.

Return ONLY a valid JSON object with this exact structure (use null for missing/unknown fields):

{{
  "policy_information": {{
    "policy_number": null,
    "policyholder_name": null,
    "effective_date_start": null,
    "effective_date_end": null
  }},
  "incident_information": {{
    "date_of_loss": null,
    "time_of_loss": null,
    "location": null,
    "description": null
  }},
  "involved_parties": {{
    "claimant_name": null,
    "claimant_contact": null,
    "third_parties": [],
    "driver_name": null,
    "driver_license": null,
    "owner_name": null
  }},
  "asset_details": {{
    "asset_type": null,
    "make": null,
    "model": null,
    "year": null,
    "vin": null,
    "plate_number": null,
    "damage_description": null,
    "estimated_damage": null
  }},
  "other": {{
    "claim_type": null,
    "report_number": null,
    "attachments": [],
    "initial_estimate": null,
    "carrier": null,
    "agency": null
  }}
}}

FNOL Document Text:
\"\"\"
{document_text}
\"\"\"

Return ONLY the JSON object. No explanation, no markdown fences.
"""


def extract_fields_with_ai(document_text: str) -> dict:
    """Send document text to Gemini and get structured field extraction."""
    prompt = EXTRACTION_PROMPT.format(document_text=document_text)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    raw = response.text.strip()

    # Strip markdown fences if Gemini adds them
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines).strip()

    return json.loads(raw)


# ─────────────────────────────────────────────
# 3. MISSING FIELD DETECTION
# ─────────────────────────────────────────────

MANDATORY_FIELDS = [
    ("policy_information", "policy_number"),
    ("policy_information", "policyholder_name"),
    ("incident_information", "date_of_loss"),
    ("incident_information", "location"),
    ("incident_information", "description"),
    ("asset_details", "asset_type"),
    ("asset_details", "estimated_damage"),
    ("other", "claim_type"),
    ("other", "initial_estimate"),
]


def find_missing_fields(extracted: dict) -> list:
    """Return list of mandatory field paths that are null/empty."""
    missing = []
    for section, field in MANDATORY_FIELDS:
        val = extracted.get(section, {}).get(field)
        if val is None or val == "" or val == []:
            missing.append(f"{section}.{field}")
    return missing


# ─────────────────────────────────────────────
# 4. ROUTING LOGIC
# ─────────────────────────────────────────────

FRAUD_KEYWORDS = ["fraud", "inconsistent", "staged", "suspicious", "fabricated", "fake"]


def route_claim(extracted: dict, missing_fields: list) -> tuple:
    """
    Apply routing rules and return (route, reasoning).

    Rules (in priority order):
    1. Fraud keywords in description  → Investigation Flag
    2. Claim type = injury            → Specialist Queue
    3. Any mandatory field missing    → Manual Review
    4. Estimated damage < 25,000      → Fast-track
    5. Default                        → Standard Review
    """
    description = (extracted.get("incident_information", {}).get("description") or "").lower()
    claim_type  = (extracted.get("other", {}).get("claim_type") or "").lower()
    estimated_damage_raw = (
        extracted.get("asset_details", {}).get("estimated_damage")
        or extracted.get("other", {}).get("initial_estimate")
    )

    # Rule 1 – Fraud check
    found_fraud_keywords = [kw for kw in FRAUD_KEYWORDS if kw in description]
    if found_fraud_keywords:
        return (
            "Investigation Flag",
            f"Description contains fraud-indicator keyword(s): {found_fraud_keywords}. Routed for investigation."
        )

    # Rule 2 – Injury claim
    if "injury" in claim_type or "bodily" in claim_type:
        return (
            "Specialist Queue",
            f"Claim type is '{claim_type}', which requires a specialist handler for injury claims."
        )

    # Rule 3 – Missing mandatory fields
    if missing_fields:
        return (
            "Manual Review",
            f"The following mandatory fields are missing: {missing_fields}. Human review required."
        )

    # Rule 4 – Fast-track vs Standard
    try:
        damage_amount = float(
            str(estimated_damage_raw)
            .replace(",", "")
            .replace("$", "")
            .replace("₹", "")
            .strip()
        )
        if damage_amount < 25000:
            return (
                "Fast-track",
                f"All mandatory fields present and estimated damage (${damage_amount:,.2f}) is below the $25,000 threshold."
            )
        else:
            return (
                "Standard Review",
                f"All mandatory fields present but estimated damage (${damage_amount:,.2f}) exceeds $25,000 threshold."
            )
    except (ValueError, TypeError):
        pass

    return (
        "Manual Review",
        "Could not determine damage amount; manual review required."
    )


# ─────────────────────────────────────────────
# 5. MAIN PROCESSOR
# ─────────────────────────────────────────────

def process_fnol(file_path: str) -> dict:
    """Full pipeline: file → extract text → AI fields → validate → route → JSON."""
    print(f"\n{'='*60}")
    print(f"Processing: {os.path.basename(file_path)}")
    print("="*60)

    print("→ Extracting text...")
    document_text = extract_text(file_path)
    if not document_text:
        print("  WARNING: No text extracted.")

    print("→ Running Gemini AI field extraction...")
    extracted_fields = extract_fields_with_ai(document_text)

    print("→ Validating mandatory fields...")
    missing_fields = find_missing_fields(extracted_fields)

    print("→ Applying routing rules...")
    route, reasoning = route_claim(extracted_fields, missing_fields)

    result = {
        "file": os.path.basename(file_path),
        "extractedFields": extracted_fields,
        "missingFields": missing_fields,
        "recommendedRoute": route,
        "reasoning": reasoning
    }

    print(f"→ Route     : {route}")
    print(f"→ Reasoning : {reasoning}")
    if missing_fields:
        print(f"→ Missing   : {missing_fields}")

    return result


# ─────────────────────────────────────────────
# 6. ENTRY POINT
# ─────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        files = sys.argv[1:]
    else:
        files = sorted(glob.glob("sample_fnols/*.pdf") + glob.glob("sample_fnols/*.txt"))
        if not files:
            print("Usage: python agent.py <file1.pdf> [file2.pdf ...]")
            print("Or place PDF/TXT files in the sample_fnols/ folder and run without arguments.")
            return

    all_results = []
    for f in files:
        if not os.path.exists(f):
            print(f"File not found: {f}")
            continue
        result = process_fnol(f)
        all_results.append(result)

    output_path = "claims_output.json"
    with open(output_path, "w") as out:
        json.dump(all_results, out, indent=2)

    print(f"\n{'='*60}")
    print(f"✅ Done! Results saved to {output_path}")
    print("="*60)
    print(f"\n{'File':<40} {'Route':<25} {'Missing'}")
    print("-"*80)
    for r in all_results:
        print(f"{r['file']:<40} {r['recommendedRoute']:<25} {len(r['missingFields'])} field(s)")


if __name__ == "__main__":
    main()