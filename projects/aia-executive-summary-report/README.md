# AIA Executive Summary Report Generator

Generates a professionally formatted PDF executive summary report for AIA, containing:

1. **Customer Segmentation** — Total customers by wealth segment (Mass, Mass Affluent, HNW, UHNW)
2. **Premiums by Channel** — Total premium volumes across Agency, Bancassurance, Digital, Broker, and Direct channels
3. **Top 10 Agents** — Highest-performing agents ranked by premium volume
4. **Fraud Hotspot Analysis** — Regions with the highest fraud amounts, claim counts, and fraud scores
5. **Competitive Analysis** — AIA Thailand vs key competitors in the Thai insurance market

## Setup

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

Generate the default report:

```bash
python generate_report.py
```

Specify a custom output path:

```bash
python generate_report.py -o reports/q4_summary.pdf
```

## Output

The script produces a multi-page A4 PDF with:

- **Cover page** with title, subtitle, and date
- **KPI strip** showing total customers, total premiums, and fraud hotspot count
- **Formatted tables** with alternating row colours and AIA brand styling
- **Narrative commentary** for each section
- **Competitive landscape** with market share comparison table
- **Page headers/footers** with AIA branding and page numbers

## Project Structure

| File | Description |
|---|---|
| `generate_report.py` | Main PDF generator (entry point) |
| `report_data.py` | Data module with all report data and dataclass models |
| `requirements.txt` | Python dependencies |
| `README.md` | This file |

## Customisation

To update the report data, edit `report_data.py` — specifically the `load_report_data()` function. Each data section uses typed dataclasses, making it straightforward to swap in live data from APIs or databases.
