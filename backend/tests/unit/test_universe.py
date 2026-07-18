"""Universe parsing: symbol normalization and constituent-table extraction."""

import pytest

from app.services.market_data import universe


def _table(rows: str) -> str:
    return f"""
    <html><body><table>
      <tr><th>Symbol</th><th>Security</th><th>GICS Sector</th>
          <th>GICS Sub-Industry</th><th>Date added</th></tr>
      {rows}
    </table></body></html>
    """


def test_to_yahoo_symbol_converts_dots():
    assert universe.to_yahoo_symbol("BRK.B") == "BRK-B"
    assert universe.to_yahoo_symbol("aapl ") == "AAPL"


def test_parse_constituents_extracts_rows(monkeypatch):
    rows = "".join(
        f"<tr><td>SYM{i}</td><td>Company {i}</td><td>Tech</td>"
        f"<td>Software</td><td>2020-01-0{(i % 9) + 1}</td></tr>"
        for i in range(450)
    )
    parsed = universe.parse_constituents(_table(rows))
    assert len(parsed) == 450
    first = parsed[0]
    assert first["symbol"] == "SYM0"
    assert first["yahoo_symbol"] == "SYM0"
    assert first["company_name"] == "Company 0"
    assert first["sector"] == "Tech"
    assert first["industry"] == "Software"
    assert str(first["date_added_to_index"]) == "2020-01-01"


def test_parse_constituents_dedupes_and_normalizes():
    brk_row = "<tr><td>BRK.B</td><td>Berkshire{}</td><td>Fin</td><td>Ins</td><td></td></tr>"
    rows = (brk_row.format("") + brk_row.format(" dup")) + "".join(
        f"<tr><td>S{i}</td><td>C{i}</td><td>T</td><td>U</td><td></td></tr>"
        for i in range(440)
    )
    parsed = universe.parse_constituents(_table(rows))
    brk = [p for p in parsed if p["symbol"] == "BRK.B"]
    assert len(brk) == 1
    assert brk[0]["yahoo_symbol"] == "BRK-B"


def test_parse_constituents_rejects_tiny_tables():
    rows = "<tr><td>AAPL</td><td>Apple</td><td>Tech</td><td>HW</td><td></td></tr>"
    with pytest.raises(universe.UniverseError, match="only 1 constituents"):
        universe.parse_constituents(_table(rows))


def test_parse_constituents_rejects_pages_without_table():
    with pytest.raises(universe.UniverseError):
        universe.parse_constituents("<html><body><p>nothing here</p></body></html>")
