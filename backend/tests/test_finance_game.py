"""Tests complets du moteur et des endpoints « Trading Replay » (Mode Finance)."""

from __future__ import annotations

import datetime
import random
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import hash_password
from app.config import Settings
from app.finance_game import (
    aggregate_eod_bars,
    evaluate_intrabar_exit,
    get_game_state,
    open_round_position,
    start_game_round,
    step_round,
)
from app.finance_warehouse import (
    save_index_constituents,
    sync_user_watchlists_to_warehouse,
    upsert_eod_bars,
    upsert_instrument,
    warehouse_db_path,
)
from app.main import create_app
from app.models import Base, User


def _settings_for(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_data_dir=tmp_path / "app_data",
        finance_data_dir=tmp_path / "finance_data",
        demo_mode=True,
    )


def _make_business_bars(
    count: int,
    *,
    start_price: float = 100.0,
    daily_delta: float = 0.5,
    start_date: datetime.date = datetime.date(2024, 1, 2),
) -> list[dict]:
    bars: list[dict] = []
    cur = start_date
    price = start_price
    while len(bars) < count:
        if cur.weekday() < 5:
            o = round(price, 2)
            c = round(max(1.0, price + daily_delta), 2)
            h = round(max(o, c) + 1.0, 2)
            l = round(max(0.5, min(o, c) - 1.0), 2)
            bars.append(
                {
                    "date": cur.isoformat(),
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "adjusted_close": c,
                    "volume": 150_000,
                }
            )
            price = c
        cur += datetime.timedelta(days=1)
    return bars


def _seed_symbol(
    db_path: Path,
    symbol: str,
    name: str,
    *,
    count: int = 220,
    start_price: float = 100.0,
    daily_delta: float = 0.4,
) -> list[dict]:
    upsert_instrument(
        db_path,
        {
            "symbol": symbol,
            "eod_ticker": symbol,
            "yahoo_symbol": symbol,
            "short_name": name,
            "long_name": f"{name} Corp.",
            "exchange": "PA",
            "currency": "EUR",
            "sector": "Industrials",
        },
    )
    bars = _make_business_bars(count, start_price=start_price, daily_delta=daily_delta)
    upsert_eod_bars(db_path, symbol, bars, source="eodhd")
    return bars


@contextmanager
def _auth_client(settings: Settings, username: str = "trader1", *, app=None):
    app = app or create_app(settings)
    origin = settings.origins[0]
    Base.metadata.create_all(app.state.engine)
    with app.state.sessions() as db:
        if not db.scalar(select(User).where(User.is_admin.is_(True))):
            db.add(User(username="__admin__", password_hash=hash_password("admin secret phrase"), is_admin=True))
        existing = db.scalar(select(User).where(User.username == username))
        if not existing:
            db.add(User(username=username, password_hash=hash_password("super secret phrase"), is_admin=False))
        db.commit()
    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        res = client.post("/api/auth/login", json={"username": username, "password": "super secret phrase"})
        assert res.status_code == 200
        yield client


def test_aggregate_bars_and_intrabar_sl_tp():
    daily = _make_business_bars(15, start_price=100.0, daily_delta=1.0)
    weekly = aggregate_eod_bars(daily, "week")
    monthly = aggregate_eod_bars(daily, "month")
    assert 2 <= len(weekly) <= 4
    assert len(monthly) == 1
    assert weekly[0]["open"] == daily[0]["open"]

    # Gap d'ouverture sous SL en Long -> exécuté à l'open
    assert evaluate_intrabar_exit(
        "long",
        {"open": 90.0, "high": 98.0, "low": 88.0, "close": 95.0},
        stop_loss=94.0,
        take_profit=110.0,
    ) == (90.0, "stop_loss")

    # Conflit intrabar SL + TP sans gap -> SL prioritaire (règle conservatrice)
    assert evaluate_intrabar_exit(
        "long",
        {"open": 100.0, "high": 115.0, "low": 92.0, "close": 108.0},
        stop_loss=95.0,
        take_profit=112.0,
    ) == (95.0, "stop_loss")

    # Short : Take-Profit touché
    assert evaluate_intrabar_exit(
        "short",
        {"open": 100.0, "high": 102.0, "low": 89.0, "close": 91.0},
        stop_loss=106.0,
        take_profit=90.0,
    ) == (90.0, "take_profit")


def test_blind_mode_hides_future_and_identity_until_finished(tmp_path: Path):
    settings = _settings_for(tmp_path)
    db_path = warehouse_db_path(settings)
    _seed_symbol(db_path, "AI.PA", "Air Liquide", count=220, start_price=120.0, daily_delta=0.5)

    res = start_game_round(
        db_path,
        "user-1",
        universe_type="all",
        timeframe="day",
        horizon_code="1m",
        blind_mode=True,
        rng=random.Random(42),
    )
    rnd = res["round"]
    assert rnd["status"] == "active"
    assert rnd["is_revealed"] is False
    assert rnd["symbol"] is None
    assert rnd["company_name"] == "Action Mystère"
    assert rnd["cutoff_date"] is None
    assert rnd["end_date"] is None
    assert rnd["buy_hold_return_pct"] is None
    assert len(rnd["bars"]) == rnd["cutoff_index"] + 1
    # Les dates visibles sont synthétiques (an 2000), pas 2024
    assert rnd["bars"][-1]["date"].startswith("2000-")

    # Ouverture Long à T0
    opened = open_round_position(db_path, "user-1", rnd["id"], side="long", size_pct=50.0)
    assert opened["round"]["position_status"] == "open"
    assert opened["round"]["entry_date"] == rnd["bars"][-1]["date"]

    # Avancer 5 bougies
    stepped = step_round(db_path, "user-1", rnd["id"], steps=5)
    assert stepped["round"]["current_step"] == 5
    assert len(stepped["round"]["bars"]) == rnd["cutoff_index"] + 6
    assert stepped["round"]["is_revealed"] is False

    # Finir la manche -> tout est révélé
    finished = step_round(db_path, "user-1", rnd["id"], steps=16)
    fin_rnd = finished["round"]
    assert fin_rnd["status"] == "finished"
    assert fin_rnd["is_revealed"] is True
    assert fin_rnd["symbol"] == "AI.PA"
    assert fin_rnd["company_name"] == "Air Liquide Corp."
    assert fin_rnd["cutoff_date"].startswith("2024-")
    assert fin_rnd["end_date"].startswith("2024-")
    assert fin_rnd["bars"][-1]["date"] == fin_rnd["end_date"]
    assert fin_rnd["pnl_amount"] > 0
    assert finished["profile"]["equity"] > 10000.0
    assert finished["profile"]["wins"] == 1
    assert finished["profile"]["rounds_played"] == 1


def test_step_stops_immediately_on_stop_loss_or_take_profit(tmp_path: Path):
    settings = _settings_for(tmp_path)
    db_path = warehouse_db_path(settings)
    # Hausse régulière (+1.0 / jour)
    _seed_symbol(db_path, "MC.PA", "LVMH", count=220, start_price=100.0, daily_delta=1.0)

    res = start_game_round(
        db_path,
        "user-sl",
        universe_type="symbol",
        universe_value="MC.PA",
        timeframe="day",
        horizon_code="1m",
        blind_mode=False,
        rng=random.Random(7),
    )
    rnd = res["round"]
    entry = rnd["current_price"]
    tp_target = round(entry + 2.5, 2)
    open_round_position(db_path, "user-sl", rnd["id"], side="long", size_pct=100.0, take_profit=tp_target)

    # Demander +10 bougies, mais TP est atteint au step 2 ou 3 -> arrêt exact sur la bougie TP
    stepped = step_round(db_path, "user-sl", rnd["id"], steps=10)
    sr = stepped["round"]
    assert sr["triggered_event"] == "take_profit"
    assert sr["position_status"] == "closed"
    assert sr["exit_reason"] == "take_profit"
    assert sr["exit_price"] == pytest.approx(tp_target, abs=0.01)
    assert sr["current_step"] < 10
    assert sr["status"] == "active"


def test_api_universes_user_isolation_short_close_and_reset(tmp_path: Path):
    settings = _settings_for(tmp_path)
    db_path = warehouse_db_path(settings)
    # Action en baisse continue (-0.4 / jour) -> Short gagnant (260j ≈ 52 semaines)
    _seed_symbol(db_path, "OR.PA", "L'Oréal", count=260, start_price=300.0, daily_delta=-0.4)
    save_index_constituents(
        db_path,
        "CAC40",
        [{"symbol": "OR.PA", "eod_ticker": "OR.PA", "name": "L'Oréal"}],
    )

    # Test watchlist universe isolation
    sync_user_watchlists_to_warehouse(
        db_path,
        user_id="wl-owner",
        watchlists=[{"id": "wl-1", "name": "Europe", "position": 0}],
        items=[{"id": "it-1", "list_id": "wl-1", "symbol": "OR.PA", "eod_ticker": "OR.PA", "name": "L'Oréal"}],
    )
    wl_round = start_game_round(
        db_path,
        "wl-owner",
        universe_type="watchlist",
        universe_value="wl-1",
        timeframe="week",
        horizon_code="1m",
        blind_mode=True,
        rng=random.Random(3),
    )
    assert wl_round["round"]["timeframe"] == "week"
    with pytest.raises(ValueError):
        start_game_round(db_path, "other-user", universe_type="watchlist", universe_value="wl-1")

    with _auth_client(settings, username="alice") as alice:

        # 1. État initial
        st0 = alice.get("/api/finance/game/state")
        assert st0.status_code == 200
        assert st0.json()["profile"]["equity"] == 10000.0
        assert st0.json()["eligible_symbols_count"] == 1

        # 2. Démarrer sur l'indice CAC40
        start_res = alice.post(
            "/api/finance/game/rounds",
            json={
                "universe_type": "index",
                "universe_value": "CAC40",
                "timeframe": "day",
                "horizon_code": "1m",
                "blind_mode": True,
            },
        )
        assert start_res.status_code == 200
        rnd_id = start_res.json()["round"]["id"]

        # 3. Ouvrir un Short (Vente)
        pos_res = alice.post(
            f"/api/finance/game/rounds/{rnd_id}/position",
            json={"side": "short", "size_pct": 100.0},
        )
        assert pos_res.status_code == 200

        # 4. Avancer 4 bougies puis clôturer manuellement sans terminer tout de suite
        alice.post(f"/api/finance/game/rounds/{rnd_id}/step", json={"steps": 4})
        cls_res = alice.post(f"/api/finance/game/rounds/{rnd_id}/close", json={"finish_now": False})
        assert cls_res.status_code == 200
        assert cls_res.json()["round"]["position_status"] == "closed"
        assert cls_res.json()["round"]["exit_reason"] == "manual"
        assert cls_res.json()["round"]["pnl_amount"] > 0
        assert cls_res.json()["round"]["status"] == "active"

        # 5. Terminer et révéler
        fin_res = alice.post(f"/api/finance/game/rounds/{rnd_id}/finish")
        assert fin_res.status_code == 200
        assert fin_res.json()["round"]["status"] == "finished"
        assert fin_res.json()["round"]["symbol"] == "OR.PA"

        # 6. Historique & consultation d'une manche passée
        st1 = alice.get("/api/finance/game/state").json()
        assert len(st1["history"]) == 1
        assert st1["profile"]["trades_taken"] == 1
        assert st1["profile"]["wins"] == 1
        hist_res = alice.get(f"/api/finance/game/rounds/{rnd_id}")
        assert hist_res.status_code == 200
        assert hist_res.json()["round"]["symbol"] == "OR.PA"

        # 7. Isolation : un autre utilisateur (bob) reçoit 404 sur la manche d'alice
        with _auth_client(settings, username="bob") as bob:
            assert bob.get(f"/api/finance/game/rounds/{rnd_id}").status_code == 404
            assert bob.post(f"/api/finance/game/rounds/{rnd_id}/finish").status_code == 404
            assert bob.get("/api/finance/game/state").json()["profile"]["rounds_played"] == 0

        # 8. Reset portefeuille
        rst_res = alice.post("/api/finance/game/reset", json={"starting_capital": 10000.0, "clear_history": True})
        assert rst_res.status_code == 200
        assert rst_res.json()["profile"]["equity"] == 10000.0
        assert rst_res.json()["profile"]["rounds_played"] == 0
        assert rst_res.json()["history"] == []


def test_start_round_insufficient_data_returns_400(tmp_path: Path):
    settings = _settings_for(tmp_path)
    db_path = warehouse_db_path(settings)
    _seed_symbol(db_path, "TINY.PA", "Tiny", count=20)
    with _auth_client(settings, username="trader_empty") as client:
        res = client.post(
            "/api/finance/game/rounds",
            json={"universe_type": "all", "timeframe": "day", "horizon_code": "1m"},
        )
        assert res.status_code == 400
        assert "EOD" in res.json()["detail"] or "Synchronisez" in res.json()["detail"]

    state = get_game_state(db_path, "nonexistent")
    assert state["eligible_symbols_count"] == 0


def test_five_year_horizon_and_timeframe_horizon_validation(tmp_path: Path):
    settings = _settings_for(tmp_path)
    db_path = warehouse_db_path(settings)
    # ~7.5 ans de séances ouvrées pour tester 5 ans en unité Mois (60 mois + 20 mois min)
    _seed_symbol(db_path, "LONG.PA", "LongHistory", count=1900, start_price=50.0, daily_delta=0.05)

    res = start_game_round(
        db_path,
        "user-5y",
        universe_type="symbol",
        universe_value="LONG.PA",
        timeframe="month",
        horizon_code="5y",
        blind_mode=True,
        rng=random.Random(11),
    )
    assert res["round"]["timeframe"] == "month"
    assert res["round"]["horizon_code"] == "5y"
    assert res["round"]["horizon_bars"] == 60

    # Horizon 5 ans refusé en unité Jour, et 1 semaine refusé en unité Mois
    with pytest.raises(ValueError):
        start_game_round(db_path, "user-5y", universe_type="all", timeframe="day", horizon_code="5y")
    with pytest.raises(ValueError):
        start_game_round(db_path, "user-5y", universe_type="all", timeframe="month", horizon_code="1w")
