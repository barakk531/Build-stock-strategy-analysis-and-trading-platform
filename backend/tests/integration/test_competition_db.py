"""Competition pipeline against real Postgres: fairness checks, risk-adjusted
leaderboard over the common window, comparison curves, cloning, and cascade
cleanup — spec §14 acceptance: strategies compare over equivalent assumptions
and results always include risk and drawdown, never total return alone."""

import os
import uuid
from datetime import date

import pandas as pd
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; start Postgres and set it to run integration tests",
)

START = date(2025, 1, 6)
END = date(2025, 6, 27)
POP_DAY = date(2025, 2, 10)
CRASH_FROM = date(2025, 6, 2)
PARAMS = {"volume_multiplier": 1.2}


@pytest.fixture()
def db():
    from app.db.session import SessionLocal

    session = SessionLocal()
    yield session
    session.close()


def _price_rows():
    dates = [d.date() for d in pd.bdate_range("2024-01-02", END)]
    rows = []
    for i, d in enumerate(dates):
        adj = 100.0 + 0.08 * i
        if d >= CRASH_FROM:
            adj = 90.0
        rows.append(
            {
                "trade_date": d,
                "open": round(adj, 4),
                "high": round(adj * 1.01, 4),
                "low": round(adj * 0.99, 4),
                "close": round(adj, 4),
                "adjusted_close": round(adj, 4),
                "volume": 2_000_000 if d == POP_DAY else 1_000_000,
                "dividend": 0.0,
                "stock_split": 0.0,
            }
        )
    return rows


@pytest.fixture()
def arena(db):
    """One synthetic stock + two processed accounts with different sizing."""
    from app.models.competition import Competition
    from app.models.paper import PaperAccount
    from app.models.stock import Stock
    from app.repositories import price_repository, stock_repository
    from app.schemas.paper import AccountCreateIn
    from app.services.paper_trading import processor
    from app.services.paper_trading import service as paper_service
    from app.services.paper_trading.config import AccountSettings
    from app.services.signals import detector

    symbol = f"ZK{uuid.uuid4().hex[:6].upper()}"
    stock_repository.upsert_constituents(
        db,
        [{"symbol": symbol, "yahoo_symbol": symbol, "company_name": "Arena"}],
        deactivate_missing=False,
    )
    stock = stock_repository.get_by_symbol(db, symbol)
    price_repository.upsert_prices(db, stock.id, _price_rows())
    detector.scan_all(db, symbols=[symbol], parameters=PARAMS)

    def make(name, size_pct):
        account = paper_service.create_account(
            db,
            AccountCreateIn(
                name=name,
                parameters=PARAMS,
                initial_cash=100_000.0,
                start_date=START,
                settings=AccountSettings(benchmark_symbol=None, position_size_percent=size_pct),
            ),
        )
        processor.process_account(db, account, through=END)
        return account

    small = make("ktest small", 10)
    big = make("ktest big", 50)

    yield {"symbol": symbol, "small": small, "big": big}

    db.query(Competition).filter(Competition.name.like("ktest %")).delete(
        synchronize_session=False
    )
    db.query(PaperAccount).filter(PaperAccount.name.like("ktest %")).delete(
        synchronize_session=False
    )
    db.query(Stock).filter(Stock.symbol == symbol).delete(synchronize_session=False)
    db.commit()


def test_fairness_flags_only_real_differences(db, arena):
    from app.services.competition.service import fairness_report

    report = fairness_report([arena["small"], arena["big"]])
    by_key = {c["key"]: c for c in report["checks"]}
    # Same start/capital/costs/benchmark/universe -> all fair.
    assert report["fair"] is True
    assert all(c["fair"] for c in report["checks"])

    # Break one dimension and it gets flagged.
    arena["big"].initial_cash = 50_000
    report = fairness_report([arena["small"], arena["big"]])
    by_key = {c["key"]: c for c in report["checks"]}
    assert report["fair"] is False
    assert by_key["initial_cash"]["fair"] is False
    assert by_key["start_date"]["fair"] is True
    arena["big"].initial_cash = 100_000  # restore (session object only)


def test_leaderboard_ranks_risk_adjusted_with_full_payload(db, arena):
    from app.models.competition import Competition, CompetitionAccount
    from app.services.competition import service

    competition = Competition(name="ktest lb")
    db.add(competition)
    db.flush()
    for account in (arena["small"], arena["big"]):
        db.add(
            CompetitionAccount(
                competition_id=competition.id, paper_account_id=account.id
            )
        )
    db.commit()

    payload = service.leaderboard(db, competition)

    assert payload["window"]["start"] == START.isoformat()
    assert payload["fairness"]["fair"] is True
    rows = payload["leaderboard"]
    assert len(rows) == 2
    assert [r["rank"] for r in rows] == [1, 2]
    for row in rows:
        m = row["metrics"]
        # Spec: risk and drawdown always present, never return alone.
        assert m["max_drawdown_pct"] is not None
        assert "sharpe_ratio" in m
        assert row["current_exposure_pct"] is not None
        assert row["parameter_summary"].startswith("SMA ")
    # Deterministic risk-adjusted ordering: rank 1 has >= Sharpe of rank 2.
    s1, s2 = (r["metrics"]["sharpe_ratio"] for r in rows)
    if s1 is not None and s2 is not None:
        assert s1 >= s2

    # Comparison payload: rebased curves start at 100 for every account.
    for name in (arena["small"].name, arena["big"].name):
        curve = payload["equity_curves"][name]
        assert curve[0][1] == pytest.approx(100.0)
        assert payload["drawdown_curves"][name][0][1] == pytest.approx(0.0)
        assert payload["monthly_returns"][name]
    assert payload["best_worst_trades"]  # the crash guarantees closed trades


def test_clone_copies_configuration_and_joins_competition(db, arena):
    from app.models.competition import Competition, CompetitionAccount
    from app.services.competition import service

    competition = Competition(name="ktest clone-comp")
    db.add(competition)
    db.commit()

    clone = service.clone_account(
        db, arena["big"], name="ktest cloned", competition_id=competition.id
    )
    assert clone.id != arena["big"].id
    assert clone.strategy_parameter_snapshot_json == arena["big"].strategy_parameter_snapshot_json
    assert clone.parameter_hash == arena["big"].parameter_hash
    assert clone.settings_json == arena["big"].settings_json
    assert float(clone.initial_cash) == float(arena["big"].initial_cash)
    assert clone.start_date == arena["big"].start_date
    assert float(clone.cash_balance) == float(clone.initial_cash)  # fresh history
    member = db.scalar(
        db.query(CompetitionAccount)
        .filter_by(competition_id=competition.id, paper_account_id=clone.id)
        .statement
    )
    assert member is not None


def test_api_round_trip_and_cascade(db, arena):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.models.competition import CompetitionAccount

    client = TestClient(app)
    created = client.post(
        "/api/v1/competitions",
        json={
            "name": "ktest api",
            "description": "sizing shoot-out",
            "account_ids": [arena["small"].id, arena["big"].id],
        },
    )
    assert created.status_code == 201, created.text
    comp_id = created.json()["id"]
    assert created.json()["account_count"] == 2

    listing = client.get("/api/v1/competitions").json()
    assert any(c["id"] == comp_id for c in listing["items"])

    board = client.get(f"/api/v1/competitions/{comp_id}/leaderboard").json()
    assert len(board["leaderboard"]) == 2
    assert board["notes"]

    # Unknown account rejected cleanly.
    bad = client.post(
        "/api/v1/competitions", json={"name": "ktest bad", "account_ids": [999999]}
    )
    assert bad.status_code == 404

    # Deleting a member account removes its membership (DB cascade).
    removed = client.delete(f"/api/v1/paper-accounts/{arena['small'].id}")
    assert removed.status_code == 204
    remaining = db.query(CompetitionAccount).filter_by(competition_id=comp_id).count()
    assert remaining == 1

    assert client.delete(f"/api/v1/competitions/{comp_id}").status_code == 204
    assert client.get(f"/api/v1/competitions/{comp_id}").status_code == 404
