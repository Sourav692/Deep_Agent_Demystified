"""
AIA Executive Summary Report — PDF Generator.

Generates a professionally formatted PDF report containing:
  1. Customer segmentation breakdown
  2. Total premiums by distribution channel
  3. Top 10 agents by premium volume
  4. Fraud hotspot analysis by region
  5. Competitive analysis: AIA vs Thai insurance market

Usage:
    python generate_report.py              # outputs aia_executive_summary.pdf
    python generate_report.py -o custom.pdf  # custom output path
"""

from __future__ import annotations

import argparse
import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from report_data import ReportData, load_report_data

# ── Colour palette ─────────────────────────────────────────────────────
AIA_RED = colors.HexColor("#C8102E")
AIA_DARK = colors.HexColor("#1A1A2E")
AIA_GREY = colors.HexColor("#4A4A4A")
AIA_LIGHT_GREY = colors.HexColor("#F5F5F5")
AIA_WHITE = colors.white
HEADER_BG = colors.HexColor("#1A1A2E")
ROW_ALT = colors.HexColor("#F9F9F9")

# ── Styles ──────────────────────────────────────────────────────────────
def _build_styles() -> dict[str, ParagraphStyle]:
    """Create all paragraph styles used in the report."""
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontSize=28,
            leading=34,
            textColor=AIA_WHITE,
            alignment=TA_CENTER,
            spaceAfter=6,
            fontName="Helvetica-Bold",
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=base["Normal"],
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#CCCCCC"),
            alignment=TA_CENTER,
            spaceAfter=4,
            fontName="Helvetica",
        ),
        "date": ParagraphStyle(
            "ReportDate",
            parent=base["Normal"],
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#AAAAAA"),
            alignment=TA_CENTER,
            fontName="Helvetica-Oblique",
        ),
        "section_heading": ParagraphStyle(
            "SectionHeading",
            parent=base["Heading1"],
            fontSize=16,
            leading=20,
            textColor=AIA_RED,
            spaceBefore=18,
            spaceAfter=8,
            fontName="Helvetica-Bold",
        ),
        "body": ParagraphStyle(
            "BodyText",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            textColor=AIA_GREY,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
            fontName="Helvetica",
        ),
        "kpi_value": ParagraphStyle(
            "KPIValue",
            parent=base["Normal"],
            fontSize=22,
            leading=26,
            textColor=AIA_RED,
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
        ),
        "kpi_label": ParagraphStyle(
            "KPILabel",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            textColor=AIA_GREY,
            alignment=TA_CENTER,
            fontName="Helvetica",
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            textColor=AIA_WHITE,
            fontName="Helvetica-Bold",
        ),
        "table_cell": ParagraphStyle(
            "TableCell",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            textColor=AIA_DARK,
            fontName="Helvetica",
        ),
        "footer": ParagraphStyle(
            "Footer",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#999999"),
            alignment=TA_CENTER,
            fontName="Helvetica",
        ),
    }


# ── Helpers ─────────────────────────────────────────────────────────────
def _fmt_usd(value: float) -> str:
    """Format a number as USD with commas."""
    return f"${value:,.2f}"


def _make_table(
    headers: list[str],
    rows: list[list[str]],
    col_widths: list[float],
    styles: dict[str, ParagraphStyle],
) -> Table:
    """Build a styled Table with header row and alternating row colours."""
    header_cells = [
        Paragraph(h, styles["table_header"]) for h in headers
    ]
    body_rows = [
        [Paragraph(cell, styles["table_cell"]) for cell in row]
        for row in rows
    ]
    table_data = [header_cells] + body_rows

    table = Table(table_data, colWidths=col_widths, repeatRows=1)

    # Base style
    ts = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), AIA_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]

    # Alternating row colours
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            ts.append(("BACKGROUND", (0, i), (-1, i), ROW_ALT))

    table.setStyle(TableStyle(ts))
    return table


def _section_divider() -> HRFlowable:
    """Return a thin horizontal rule used between sections."""
    return HRFlowable(
        width="100%",
        thickness=0.5,
        color=colors.HexColor("#DDDDDD"),
        spaceBefore=6,
        spaceAfter=12,
    )


def _kpi_card(value: str, label: str, styles: dict) -> Table:
    """Build a single KPI card as a small table."""
    card_data = [
        [Paragraph(value, styles["kpi_value"])],
        [Paragraph(label, styles["kpi_label"])],
    ]
    card = Table(card_data, colWidths=[5.5 * cm])
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), AIA_LIGHT_GREY),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
                ("ROUNDEDCORNERS", [4, 4, 4, 4]),
            ]
        )
    )
    return card


# ── Page callbacks ──────────────────────────────────────────────────────
def _header_footer(canvas, doc: SimpleDocTemplate) -> None:
    """Draw page header line and footer on every page."""
    canvas.saveState()
    width, height = A4

    # Top accent line
    canvas.setStrokeColor(AIA_RED)
    canvas.setLineWidth(2)
    canvas.line(1.5 * cm, height - 1.2 * cm, width - 1.5 * cm, height - 1.2 * cm)

    # Footer
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#999999"))
    canvas.drawCentredString(
        width / 2,
        1.0 * cm,
        f"AIA Executive Summary  •  Confidential  •  Page {doc.page}",
    )
    canvas.restoreState()


# ── Cover page ──────────────────────────────────────────────────────────
def _build_cover(data: ReportData, styles: dict) -> list:
    """Return flowables for the cover page."""
    today = datetime.date.today()
    today_display = today.strftime("%B %d, %Y")
    today_iso = today.strftime("%Y-%m-%d")

    # Dark background table acting as a cover card
    cover_content = [
        [Paragraph(data.report_title, styles["title"])],
        [Paragraph(data.report_subtitle, styles["subtitle"])],
        [Spacer(1, 12)],
        [Paragraph(today_display, styles["date"])],
    ]
    cover_table = Table(cover_content, colWidths=[16 * cm])
    cover_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), AIA_DARK),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 30),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 30),
                ("LEFTPADDING", (0, 0), (-1, -1), 20),
                ("RIGHTPADDING", (0, 0), (-1, -1), 20),
                ("ROUNDEDCORNERS", [8, 8, 8, 8]),
            ]
        )
    )

    return [
        Spacer(1, 5 * cm),
        cover_table,
        Spacer(1, 2 * cm),
        Paragraph(
            f"Prepared by AIA Analytics  •  Data as of {today_iso}",
            styles["body"],
        ),
        PageBreak(),
    ]


# ── Section builders ────────────────────────────────────────────────────
def _build_kpi_strip(data: ReportData, styles: dict) -> list:
    """Build the top-level KPI summary strip."""
    cards = [
        _kpi_card(f"{data.total_customers:,}", "Total Customers", styles),
        _kpi_card(_fmt_usd(data.total_premiums_usd), "Total Premiums", styles),
        _kpi_card(str(len(data.fraud_hotspots)), "Fraud Hotspot Regions", styles),
    ]
    strip = Table([cards], colWidths=[6 * cm, 6 * cm, 6 * cm])
    strip.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return [
        Paragraph("Key Performance Indicators", styles["section_heading"]),
        _section_divider(),
        strip,
        Spacer(1, 10),
    ]


def _build_customer_section(data: ReportData, styles: dict) -> list:
    """Build the customer segmentation section."""
    rows = [
        [
            seg.name,
            f"{seg.count:,}",
            f"{seg.count / data.total_customers:.1%}" if data.total_customers else "0.0%",
        ]
        for seg in data.customer_segments
    ]
    rows.append(["Total", f"{data.total_customers:,}", "100.0%"])

    table = _make_table(
        headers=["Segment", "Customers", "Share"],
        rows=rows,
        col_widths=[7 * cm, 5 * cm, 5 * cm],
        styles=styles,
    )

    return [
        Paragraph("1 &nbsp;|&nbsp; Customer Segmentation", styles["section_heading"]),
        _section_divider(),
        Paragraph(
            f"AIA's customer base of <b>{data.total_customers:,}</b> customers spans four wealth segments. "
            "The Mass segment represents the largest cohort (48.7%), while Ultra High "
            "Net Worth customers — though only 5.2% of the base — represent outsized "
            "premium and lifetime-value potential.",
            styles["body"],
        ),
        Spacer(1, 4),
        table,
        Spacer(1, 10),
    ]


def _build_channel_section(data: ReportData, styles: dict) -> list:
    """Build the premiums-by-channel section."""
    rows = [
        [
            cp.channel,
            _fmt_usd(cp.premium_usd),
            f"{cp.premium_usd / data.total_premiums_usd:.1%}" if data.total_premiums_usd else "0.0%",
        ]
        for cp in data.channel_premiums
    ]
    rows.append(["Total", _fmt_usd(data.total_premiums_usd), "100.0%"])

    table = _make_table(
        headers=["Channel", "Premium (USD)", "Share"],
        rows=rows,
        col_widths=[6 * cm, 6 * cm, 5 * cm],
        styles=styles,
    )

    return [
        Paragraph(
            "2 &nbsp;|&nbsp; Total Premiums by Distribution Channel",
            styles["section_heading"],
        ),
        _section_divider(),
        Paragraph(
            "Agency remains the dominant channel at <b>$2.44M</b> (30.4%), closely "
            "followed by Bancassurance ($2.23M). Digital channels contribute $1.86M, "
            "reflecting AIA's ongoing digital transformation investment.",
            styles["body"],
        ),
        Spacer(1, 4),
        table,
        Spacer(1, 10),
    ]


def _build_agents_section(data: ReportData, styles: dict) -> list:
    """Build the top-10 agents section."""
    rows = [
        [
            str(a.rank),
            a.name,
            a.agent_id,
            a.channel,
            _fmt_usd(a.premium_usd),
        ]
        for a in data.top_agents
    ]

    table = _make_table(
        headers=["#", "Agent Name", "ID", "Channel", "Premium (USD)"],
        rows=rows,
        col_widths=[1.2 * cm, 4.5 * cm, 3 * cm, 3.5 * cm, 4.8 * cm],
        styles=styles,
    )

    return [
        Paragraph("3 &nbsp;|&nbsp; Top 10 Agents by Premium Volume", styles["section_heading"]),
        _section_divider(),
        Paragraph(
            "The top-performing agent, <b>Hui Garcia</b>, generated $270K in premiums "
            "through the Direct channel. Notably, Digital-channel agents occupy three of "
            "the top five positions, underscoring the channel's growing importance.",
            styles["body"],
        ),
        Spacer(1, 4),
        table,
        Spacer(1, 10),
    ]


def _build_fraud_section(data: ReportData, styles: dict) -> list:
    """Build the fraud hotspots section."""
    rows = [
        [
            fh.region,
            _fmt_usd(fh.total_fraud_amount_usd),
            str(fh.claim_count),
            f"{fh.avg_fraud_score:.2f}",
        ]
        for fh in data.fraud_hotspots
    ]

    table = _make_table(
        headers=["Region", "Fraud Amount (USD)", "Claims", "Avg Fraud Score"],
        rows=rows,
        col_widths=[4 * cm, 5 * cm, 3.5 * cm, 4.5 * cm],
        styles=styles,
    )

    return [
        Paragraph("4 &nbsp;|&nbsp; Fraud Hotspot Analysis", styles["section_heading"]),
        _section_divider(),
        Paragraph(
            "<b>Hong Kong</b> is the top fraud hotspot with $2.8M in flagged claims across "
            "54 cases. Indonesia shows the highest average fraud score (0.82), suggesting "
            "more concentrated but higher-confidence fraud signals. Total flagged fraud "
            "across the top 5 regions exceeds <b>$10.5M</b>.",
            styles["body"],
        ),
        Spacer(1, 4),
        table,
        Spacer(1, 10),
    ]


def _build_competitive_section(data: ReportData, styles: dict) -> list:
    """Build the competitive analysis section."""
    rows = [
        [c.company, c.profile, c.market_share]
        for c in data.competitors
    ]

    table = _make_table(
        headers=["Company", "Profile", "Market Share"],
        rows=rows,
        col_widths=[4.5 * cm, 8 * cm, 4.5 * cm],
        styles=styles,
    )

    return [
        PageBreak(),
        Paragraph(
            "5 &nbsp;|&nbsp; Competitive Analysis — Thai Insurance Market",
            styles["section_heading"],
        ),
        _section_divider(),
        Paragraph(data.competitive_narrative, styles["body"]),
        Spacer(1, 8),
        table,
        Spacer(1, 12),
        Paragraph(
            "<b>AIA Strengths:</b> Largest agency force (50,000+ agents), 52.7% share of "
            "individual health insurance, Premier Agency model with ~3× productivity vs. "
            "non-FA agents, and growing digital investment.",
            styles["body"],
        ),
        Paragraph(
            "<b>Key Competitive Risks:</b> Bancassurance-strong challengers (FWD/SCB, "
            "Muang Thai/KBank, Krungthai-AXA) and the need to accelerate digital "
            "distribution, which grew 28.2% YoY but remains only ~0.2% of total premiums.",
            styles["body"],
        ),
        Paragraph(
            "<b>Market Outlook:</b> Thai GWP totalled THB 636.7B (~$18.3B) in 2023; "
            "H1 2025 grew 4.87% YoY. Life insurance penetration at ~3.7-4.1% of GDP "
            "(vs. ~7.4% global average) signals significant growth headroom. Health rider "
            "premiums surged 19% YoY. Market CAGR projected >4% through 2028.",
            styles["body"],
        ),
    ]


# ── Main PDF assembly ──────────────────────────────────────────────────
def generate_pdf(output_path: str = "aia_executive_summary.pdf") -> str:
    """
    Generate the full AIA Executive Summary PDF.

    Args:
        output_path: File path for the generated PDF.

    Returns:
        The absolute path of the generated PDF file.
    """
    data = load_report_data()
    styles = _build_styles()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        title=data.report_title,
        author="AIA Analytics",
    )

    # Assemble all flowables
    story: list = []
    story.extend(_build_cover(data, styles))
    story.extend(_build_kpi_strip(data, styles))
    story.extend(_build_customer_section(data, styles))
    story.extend(_build_channel_section(data, styles))
    story.extend(_build_agents_section(data, styles))
    story.extend(_build_fraud_section(data, styles))
    story.extend(_build_competitive_section(data, styles))

    # Final note
    story.append(Spacer(1, 20))
    story.append(
        HRFlowable(
            width="100%", thickness=1, color=AIA_RED, spaceBefore=10, spaceAfter=10
        )
    )
    story.append(
        Paragraph(
            "End of Report  •  Confidential  •  AIA Group",
            styles["footer"],
        )
    )

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)

    resolved = str(Path(output_path).resolve())
    print(f"✅ Report generated: {resolved}")
    return resolved


# ── CLI entry point ─────────────────────────────────────────────────────
def main() -> None:
    """Parse CLI arguments and generate the report."""
    parser = argparse.ArgumentParser(
        description="Generate the AIA Executive Summary PDF report."
    )
    parser.add_argument(
        "-o",
        "--output",
        default="aia_executive_summary.pdf",
        help="Output PDF file path (default: aia_executive_summary.pdf)",
    )
    args = parser.parse_args()
    generate_pdf(args.output)


if __name__ == "__main__":
    main()
