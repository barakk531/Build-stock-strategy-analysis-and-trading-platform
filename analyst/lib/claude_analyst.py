"""Anthropic Claude analysis: bull/bear case, deep dive, macro pulse-check.

Uses the official `anthropic` SDK with Claude Opus 4.8 and adaptive thinking,
streaming the response so long generations never hit an HTTP timeout. The user
supplies ANTHROPIC_API_KEY in .env; a missing key or any error yields a
friendly message instead of raising, so a page never crashes.

Compliance: the system prompt forbids buy/hold/sell recommendations and price
targets. The model is given already-computed facts as input (no tools, no
network) and writes neutral, educational prose. Model output is untrusted —
pages render it as text, never execute it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from lib.config import anthropic_api_key

MODEL = "claude-opus-4-8"
MAX_TOKENS = 2500

SYSTEM_PROMPT = (
    "You are an educational markets analyst for a personal research dashboard. "
    "Your audience is a single individual studying a security for their own "
    "learning. Explain what the data shows in clear, neutral language.\n\n"
    "Hard rules (compliance):\n"
    "- NEVER give a buy, hold, or sell recommendation, and never imply one.\n"
    "- NEVER state or predict a price target.\n"
    "- Do not tell the reader what they 'should' do.\n"
    "- Frame everything as observations and educational context, not advice.\n"
    "- Note uncertainty and that past or simulated performance does not "
    "guarantee future results.\n"
    "- Base your analysis only on the facts provided in the user message; if a "
    "figure is missing, say so rather than inventing it.\n\n"
    "Use plain, factual phrasing (e.g. 'margins are higher than the sector "
    "median', 'the stock trades below its 200-day average'). Keep it concise "
    "and well-structured with short markdown headings."
)

_MESSAGE_MISSING_KEY = (
    "🔑 **Claude analysis is unavailable.** Set `ANTHROPIC_API_KEY` in your "
    "`.env` file to enable AI-generated analysis. This is optional — every "
    "other part of the dashboard works without it."
)


def available() -> bool:
    """True when an API key is configured (does not validate it)."""
    return anthropic_api_key() is not None


def _client():
    """Construct the SDK client, or None if the SDK/key is unavailable."""
    key = anthropic_api_key()
    if not key:
        return None
    try:
        import anthropic

        return anthropic.Anthropic(api_key=key)
    except Exception:
        return None


def _facts_block(facts: dict) -> str:
    """Serialize the computed facts as compact JSON for the prompt."""
    try:
        return json.dumps(facts, default=str, indent=2)[:8000]
    except Exception:
        return str(facts)[:8000]


_PROMPTS = {
    "bull_bear": (
        "Write a balanced bull case and bear case for {name} ({ticker}), based "
        "strictly on the facts below. Use two short markdown sections, "
        "'## Bull case' and '## Bear case', each with 3-5 concise bullet points "
        "grounded in the numbers. Do not conclude with a recommendation.\n\n"
        "Facts:\n{facts}"
    ),
    "deep": (
        "Write a neutral, educational deep-dive on {name} ({ticker}) using only "
        "the facts below. Cover, with short markdown headings: business and "
        "sector context, profitability and balance-sheet observations, "
        "valuation context relative to typical ranges, technical posture "
        "(trend/momentum/position), and key risks to understand. End with a "
        "one-line reminder that this is educational and not advice. Do not give "
        "a recommendation or a price target.\n\nFacts:\n{facts}"
    ),
    "macro": (
        "Write a short, educational 'macro pulse-check' interpreting the U.S. "
        "macro indicators below for a personal-research reader. Explain what the "
        "current readings and recent direction suggest about the economic "
        "backdrop in neutral terms, note tensions or mixed signals, and avoid "
        "any market timing or investment advice. Use brief markdown sections.\n\n"
        "Indicators:\n{facts}"
    ),
}


def _stream(kind: str, **fields) -> Iterator[str]:
    """Yield text chunks from a Claude generation. Never raises."""
    if not available():
        yield _MESSAGE_MISSING_KEY
        return
    client = _client()
    if client is None:
        yield (
            "⚠️ The `anthropic` package is not installed. Run "
            "`pip install anthropic` to enable AI analysis."
        )
        return

    prompt = _PROMPTS[kind].format(**fields)
    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield text
            final = stream.get_final_message()
        if final.stop_reason == "refusal":
            yield (
                "\n\n_Claude declined to complete this analysis. Try a different "
                "symbol or rephrase the request._"
            )
    except Exception as exc:  # network, auth, rate limit, etc.
        yield f"⚠️ Claude analysis failed: {exc}"


def bull_bear_stream(ticker: str, name: str, facts: dict) -> Iterator[str]:
    return _stream("bull_bear", ticker=ticker, name=name or ticker, facts=_facts_block(facts))


def deep_analysis_stream(ticker: str, name: str, facts: dict) -> Iterator[str]:
    return _stream("deep", ticker=ticker, name=name or ticker, facts=_facts_block(facts))


def macro_pulse_stream(snapshots: dict) -> Iterator[str]:
    return _stream("macro", facts=_facts_block(snapshots))
