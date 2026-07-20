"""Curated ETF peer groups + expense ratios for cost comparison.

Expense ratios are curated static values (percent per year) — they change
rarely and Yahoo's field coverage is spotty. get_expense_ratio prefers a live
value when available and falls back to this table.
"""

from __future__ import annotations

# Peer groups: same exposure, comparable on cost.
PEER_GROUPS: dict[str, list[str]] = {
    "S&P 500": ["SPY", "VOO", "IVV", "SPLG", "RSP"],
    "Total US market": ["VTI", "ITOT", "SCHB", "SCHX"],
    "Nasdaq 100": ["QQQ", "QQQM"],
    "Small caps": ["IWM", "VTWO", "VB", "IJR", "VIOO"],
    "Mid caps": ["MDY", "IJH", "VO"],
    "Dow Jones": ["DIA"],
    "US growth": ["VUG", "SCHG", "IWF", "VOOG"],
    "US value": ["VTV", "SCHV", "IWD"],
    "Dividend": ["VYM", "SCHD", "HDV", "DVY", "VIG", "DGRO"],
    "Covered call": ["JEPI", "JEPQ"],
    "Intl developed": ["VEA", "IEFA", "EFA", "VXUS", "IXUS"],
    "Emerging markets": ["VWO", "IEMG", "EEM"],
    "Aggregate bond": ["AGG", "BND", "SCHZ"],
    "Treasuries long": ["TLT", "IEF", "SHY"],
    "Corporate bond": ["LQD", "HYG", "JNK"],
    "Gold": ["GLD", "IAU", "GLDM"],
    "Silver": ["SLV"],
    "Real estate": ["VNQ", "SCHH", "XLRE"],
    "Technology": ["XLK", "VGT", "FTEC"],
    "Semiconductors": ["SMH", "SOXX"],
    "Financials": ["XLF", "VFH", "KRE"],
    "Health care": ["XLV", "VHT", "IBB", "XBI"],
    "Energy": ["XLE", "VDE", "XOP"],
    "Industrials": ["XLI", "VIS"],
    "Cons. discretionary": ["XLY", "VCR"],
    "Cons. staples": ["XLP", "VDC"],
    "Utilities": ["XLU", "VPU"],
    "Materials": ["XLB", "VAW"],
    "Communication": ["XLC", "VOX"],
    "Factor": ["QUAL", "MTUM", "USMV"],
    "Thematic/crypto": ["ARKK", "IBIT", "FBTC", "BITO"],
}

# Percent per year. Curated 2025/2026 sticker rates.
EXPENSE_RATIOS: dict[str, float] = {
    "SPY": 0.0945, "VOO": 0.03, "IVV": 0.03, "SPLG": 0.02, "RSP": 0.20,
    "VTI": 0.03, "ITOT": 0.03, "SCHB": 0.03, "SCHX": 0.03,
    "QQQ": 0.20, "QQQM": 0.15,
    "IWM": 0.19, "VTWO": 0.07, "VB": 0.05, "IJR": 0.06, "VIOO": 0.10,
    "MDY": 0.23, "IJH": 0.05, "VO": 0.04,
    "DIA": 0.16,
    "VUG": 0.04, "SCHG": 0.04, "IWF": 0.18, "VOOG": 0.07,
    "VTV": 0.04, "SCHV": 0.04, "IWD": 0.18,
    "VYM": 0.06, "SCHD": 0.06, "HDV": 0.08, "DVY": 0.38, "VIG": 0.05, "DGRO": 0.08,
    "JEPI": 0.35, "JEPQ": 0.35,
    "VEA": 0.03, "IEFA": 0.07, "EFA": 0.32, "VXUS": 0.05, "IXUS": 0.07,
    "VWO": 0.08, "IEMG": 0.09, "EEM": 0.68,
    "AGG": 0.03, "BND": 0.03, "SCHZ": 0.03,
    "TLT": 0.15, "IEF": 0.15, "SHY": 0.15,
    "LQD": 0.14, "HYG": 0.49, "JNK": 0.40,
    "GLD": 0.40, "IAU": 0.25, "GLDM": 0.10, "SLV": 0.50,
    "VNQ": 0.13, "SCHH": 0.07, "XLRE": 0.09,
    "XLK": 0.09, "VGT": 0.09, "FTEC": 0.084, "SMH": 0.35, "SOXX": 0.35,
    "XLF": 0.09, "VFH": 0.09, "KRE": 0.35,
    "XLV": 0.09, "VHT": 0.09, "IBB": 0.45, "XBI": 0.35,
    "XLE": 0.09, "VDE": 0.09, "XOP": 0.35,
    "XLI": 0.09, "VIS": 0.09,
    "XLY": 0.09, "VCR": 0.09,
    "XLP": 0.09, "VDC": 0.09,
    "XLU": 0.09, "VPU": 0.09,
    "XLB": 0.09, "VAW": 0.09,
    "XLC": 0.09, "VOX": 0.09,
    "QUAL": 0.15, "MTUM": 0.15, "USMV": 0.15,
    "ARKK": 0.75, "IBIT": 0.25, "FBTC": 0.25, "BITO": 0.95,
    "USO": 0.70,
}


def find_peer_group(ticker: str) -> tuple[str, list[str]] | None:
    """(group name, peer tickers) containing this ETF, or None."""
    ticker = (ticker or "").upper()
    for name, members in PEER_GROUPS.items():
        if ticker in members:
            return name, members
    return None


def get_expense_ratio(ticker: str, live_value: float | None = None) -> float | None:
    """Expense ratio in percent/yr — live value first, curated fallback."""
    if live_value is not None and 0 < float(live_value) < 5:
        return float(live_value)
    return EXPENSE_RATIOS.get((ticker or "").upper())


def cheaper_alternatives(ticker: str, position_usd: float = 100_000.0) -> list[dict]:
    """Peers with a lower expense ratio + annual savings on `position_usd`.

    Returns [{"ticker","expense_ratio","savings_bps","savings_usd"}] sorted by
    savings, or [] when no group / nothing cheaper.
    """
    ticker = (ticker or "").upper()
    group = find_peer_group(ticker)
    own = get_expense_ratio(ticker)
    if group is None or own is None:
        return []
    out = []
    for peer in group[1]:
        if peer == ticker:
            continue
        peer_er = get_expense_ratio(peer)
        if peer_er is None or peer_er >= own:
            continue
        delta_pct = own - peer_er
        out.append({
            "ticker": peer,
            "expense_ratio": peer_er,
            "savings_bps": round(delta_pct * 100, 1),
            "savings_usd": round(position_usd * delta_pct / 100.0, 2),
        })
    out.sort(key=lambda r: r["savings_usd"], reverse=True)
    return out
