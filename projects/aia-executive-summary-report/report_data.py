"""
Static data module for the AIA Executive Summary Report.

Contains all data pulled from AIA analytics systems (customer, distribution,
claims) and competitive research, structured for consumption by the PDF generator.
"""

from dataclasses import dataclass, field


@dataclass
class CustomerSegment:
    """A single customer segment with its count."""
    name: str
    count: int


@dataclass
class ChannelPremium:
    """Premium volume for a distribution channel."""
    channel: str
    premium_usd: float


@dataclass
class TopAgent:
    """A top-performing agent record."""
    rank: int
    name: str
    agent_id: str
    channel: str
    premium_usd: float


@dataclass
class FraudHotspot:
    """Fraud metrics for a region."""
    region: str
    total_fraud_amount_usd: float
    claim_count: int
    avg_fraud_score: float


@dataclass
class Competitor:
    """A competitor profile row."""
    company: str
    profile: str
    market_share: str


@dataclass
class ReportData:
    """All data needed to render the executive summary PDF."""

    report_title: str = "AIA Executive Summary Report"
    report_subtitle: str = "Insurance Analytics & Competitive Intelligence"

    # --- Section 1: Customer Segmentation ---
    customer_segments: list[CustomerSegment] = field(default_factory=list)
    total_customers: int = 0

    # --- Section 2: Premiums by Channel ---
    channel_premiums: list[ChannelPremium] = field(default_factory=list)
    total_premiums_usd: float = 0.0

    # --- Section 3: Top 10 Agents ---
    top_agents: list[TopAgent] = field(default_factory=list)

    # --- Section 4: Fraud Hotspots ---
    fraud_hotspots: list[FraudHotspot] = field(default_factory=list)

    # --- Section 5: Competitive Analysis ---
    competitors: list[Competitor] = field(default_factory=list)
    competitive_narrative: str = ""


def load_report_data() -> ReportData:
    """Return the full dataset for the executive summary report."""

    data = ReportData()

    # ── Customer Segments ──────────────────────────────────────────────
    data.customer_segments = [
        CustomerSegment("Mass", 973),
        CustomerSegment("Mass Affluent", 654),
        CustomerSegment("High Net Worth", 269),
        CustomerSegment("Ultra High Net Worth", 104),
    ]
    data.total_customers = sum(s.count for s in data.customer_segments)

    # ── Premiums by Channel ────────────────────────────────────────────
    data.channel_premiums = [
        ChannelPremium("Agency", 2_444_070.17),
        ChannelPremium("Bancassurance", 2_229_614.30),
        ChannelPremium("Digital", 1_862_174.12),
        ChannelPremium("Broker", 962_571.50),
        ChannelPremium("Direct", 526_333.07),
    ]
    data.total_premiums_usd = sum(c.premium_usd for c in data.channel_premiums)

    # ── Top 10 Agents ──────────────────────────────────────────────────
    data.top_agents = [
        TopAgent(1, "Hui Garcia", "AGT-0048", "Direct", 270_153.95),
        TopAgent(2, "Raj Chen", "AGT-0016", "Agency", 242_296.73),
        TopAgent(3, "Maria Wong", "AGT-0029", "Digital", 239_222.59),
        TopAgent(4, "Raj Sharma", "AGT-0017", "Digital", 214_177.28),
        TopAgent(5, "Rizal Wijaya", "AGT-0042", "Digital", 211_832.30),
        TopAgent(6, "Li Rahman", "AGT-0006", "Broker", 201_801.84),
        TopAgent(7, "Lee Wijaya", "AGT-0037", "Bancassurance", 199_941.59),
        TopAgent(8, "Siti Suzuki", "AGT-0005", "Agency", 198_878.35),
        TopAgent(9, "Lee Lin", "AGT-0022", "Agency", 198_491.75),
        TopAgent(10, "Emma Pham", "AGT-0003", "Bancassurance", 195_741.53),
    ]

    # ── Fraud Hotspots ─────────────────────────────────────────────────
    data.fraud_hotspots = [
        FraudHotspot("Hong Kong", 2_803_867.20, 54, 0.80),
        FraudHotspot("Singapore", 2_433_572.16, 40, 0.74),
        FraudHotspot("Thailand", 2_039_737.74, 25, 0.81),
        FraudHotspot("Indonesia", 1_620_667.30, 18, 0.82),
        FraudHotspot("Philippines", 1_605_291.96, 27, 0.80),
    ]

    # ── Competitive Analysis ───────────────────────────────────────────
    data.competitors = [
        Competitor("AIA Thailand", "Foreign (HK-listed AIA Group); agency-led; 50,000+ agents", "~26%"),
        Competitor("FWD Life Insurance", "Foreign (FWD Group); merged with SCB Life in 2021", "~13%"),
        Competitor("Thai Life Insurance", "Domestic; IPO in 2023; sole Thai-owned top-5 player", "~12-14%"),
        Competitor("Muang Thai Life", "Domestic; backed by KasikornBank bancassurance", "~11%"),
        Competitor("Krungthai-AXA Life", "JV (Krungthai Bank + AXA); bancassurance-led", "~7%"),
        Competitor("Prudential Thailand", "Foreign (Prudential plc); investment focus", "~6.5%"),
        Competitor("Allianz Ayudhya", "Foreign (Allianz SE); acquired Aetna Thai entities", "~6%"),
        Competitor("Bangkok Life Assurance", "Domestic; linked to Bangkok Bank", "~4-6%"),
    ]

    data.competitive_narrative = (
        "AIA Thailand holds a structurally dominant position with ~26% market share — "
        "nearly 2× its nearest rival (FWD at ~13%). AIA commands the largest agency "
        "network (50,000+ agents) and an overwhelming 52.7% share of individual health "
        "insurance sales. The Thai life insurance market totalled THB 636.7B (~$18.3B) "
        "in 2023 GWP, with H1 2025 growing 4.87% YoY. New business premiums rose 7.38% "
        "in H1 2025.\n\n"
        "Life insurance penetration remains low at ~3.7-4.1% of GDP (vs. ~7.4% global "
        "average), signalling significant growth headroom. An aging population (life "
        "expectancy 77.9 years) is driving demand for whole-life and pension products. "
        "Health rider premiums surged 19% YoY in H1 2025, fuelled by post-COVID awareness "
        "and ~15% medical inflation. Digital channel premiums grew 28.2% YoY but still "
        "represent only ~0.2% of total premiums. The market is projected to grow at >4% "
        "CAGR through 2028."
    )

    return data
