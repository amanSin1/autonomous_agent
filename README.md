# Autonomous Insurance Claims Processing Agent

An AI-powered Python agent that reads FNOL (First Notice of Loss) documents, extracts key fields, detects missing data, and automatically routes each claim to the correct workflow — using Google Gemini AI (free).

---

## What It Does

Insurance companies receive hundreds of claim forms daily. Instead of a human reading each one, this agent:

1. Reads the PDF or TXT claim document
2. Uses Gemini AI to extract 20+ structured fields
3. Checks which mandatory fields are missing
4. Automatically routes the claim based on rules
5. Saves everything as JSON

---

## Project Structure

```
insurance_agent/
├── agent.py                        # All logic — single file
├── requirements.txt                # Python dependencies
├── .env                            # Your Gemini API key (not committed)
├── claims_output.json              # Output generated after each run
└── sample_fnols/                   # Sample claim documents
    ├── fnol_001_fast_track.txt
    ├── fnol_002_missing_fields.txt
    ├── fnol_003_fraud_flag.txt
    └── fnol_004_injury.txt
```

---

## Setup

### 1. Clone the repository
```bash
git remote add origin https://github.com/amanSin1/autonomous_agent.git
cd insurance-claims-agent
```

### 2. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate        # Mac / Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Add your Gemini API key
Create a `.env` file:
```
GEMINI_API_KEY=your_key_here
```
Get a free key (no credit card) at: https://aistudio.google.com

---

## Running the Agent

Process all files in the `sample_fnols/` folder:
```bash
python agent.py
```

Process specific files:
```bash
python agent.py path/to/claim1.pdf path/to/claim2.pdf
```

Supported formats: `.pdf` and `.txt`

---

## Output Format

Results are saved to `claims_output.json`:

```json
{
  "file": "fnol_001_fast_track.txt",
  "extractedFields": {
    "policy_information": {
      "policy_number": "AUTO-2024-887432",
      "policyholder_name": "James R. Mitchell",
      "effective_date_start": "01/01/2024",
      "effective_date_end": "12/31/2024"
    },
    "incident_information": {
      "date_of_loss": "March 15, 2024",
      "time_of_loss": "2:35 PM",
      "location": "142 Maple Street, Columbus, OH 43215",
      "description": "Insured vehicle was rear-ended while stopped at a red light..."
    },
    "asset_details": {
      "estimated_damage": "$8,500"
    },
    "other": {
      "claim_type": "Property Damage"
    }
  },
  "missingFields": [],
  "recommendedRoute": "Fast-track",
  "reasoning": "All mandatory fields present and estimated damage ($8,500.00) is below the $25,000 threshold."
}
```

---

## Routing Rules

| Priority | Condition | Route |
|---|---|---|
| 1 | Description contains: `fraud`, `staged`, `inconsistent`, `suspicious` | Investigation Flag |
| 2 | Claim type = injury / bodily injury | Specialist Queue |
| 3 | Any mandatory field is missing | Manual Review |
| 4 | Estimated damage < $25,000 | Fast-track |
| 5 | Estimated damage >= $25,000 | Standard Review |

---

## Sample Results

| File | Route | Missing Fields |
|---|---|---|
| fnol_001_fast_track.txt | Fast-track | 0 |
| fnol_002_missing_fields.txt | Manual Review | 2 (no damage estimate) |
| fnol_003_fraud_flag.txt | Investigation Flag | 0 |
| fnol_004_injury.txt | Specialist Queue | 0 |

---

## How It Works — Step by Step

**Step 1 — Text extraction**
`pdfplumber` reads all text from the document. Falls back to `pypdf` if needed.

**Step 2 — AI field extraction**
The full document text is sent to Google Gemini with a structured prompt. Gemini returns a clean JSON object with all 20+ fields filled where available, and `null` where data is missing.

**Step 3 — Validation**
The agent checks 9 mandatory fields. Any that are `null` or empty are added to the `missingFields` list.

**Step 4 — Routing**
Rules are applied in priority order (fraud check first, then injury, then missing fields, then damage amount). The first matching rule wins.

**Step 5 — Output**
All results are written to `claims_output.json` and a summary table is printed to the terminal.

---

## Dependencies

| Package | Purpose |
|---|---|
| `google-genai` | Google Gemini AI API |
| `pdfplumber` | PDF text extraction |
| `pypdf` | PDF fallback reader |
| `python-dotenv` | Load API key from .env |

---

## Notes

- The `.env` file is gitignored — your API key is never committed
- Works with any FNOL document in PDF or TXT format
- Gemini 2.5 Flash is used — fast and free tier available
