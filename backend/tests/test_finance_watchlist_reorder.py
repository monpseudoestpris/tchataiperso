"""Tests du réordonnancement des actions dans les listes de suivi (`PATCH /api/finance/watchlists/{list_id}/reorder`)."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import hash_password
from app.config import Settings
from app.finance_warehouse import load_user_watchlists_from_warehouse, warehouse_db_path
from app.main import create_app
from app.models import Base, FinanceWatchlist, FinanceWatchlistItem, User


def _settings_for(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_data_dir=tmp_path / "app_data",
        finance_data_dir=tmp_path / "finance_data",
        demo_mode=True,
    )


@contextmanager
def _auth_client(app, origin: str, username: str):
    with app.state.sessions() as db:
        if not db.scalar(select(User).where(User.is_admin.is_(True))):
            db.add(User(username="__admin__", password_hash=hash_password("admin secret phrase"), is_admin=True))
        if not db.scalar(select(User).where(User.username == username)):
            db.add(User(username=username, password_hash=hash_password("super secret phrase"), is_admin=False))
        db.commit()
    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        res = client.post("/api/auth/login", json={"username": username, "password": "super secret phrase"})
        assert res.status_code == 200
        yield client


def test_reorder_watchlist_persists_db_warehouse_and_enforces_isolation(tmp_path: Path):
    settings = _settings_for(tmp_path)
    app = create_app(settings)
    origin = settings.origins[0]
    Base.metadata.create_all(app.state.engine)

    with _auth_client(app, origin, "alice") as alice:
        # Créer une liste et y insérer 3 actions directement en DB
        wl_res = alice.post("/api/finance/watchlists", json={"name": "PEA"})
        assert wl_res.status_code == 201
        list_id = wl_res.json()["id"]

        with app.state.sessions() as db:
            user = db.scalar(select(User).where(User.username == "alice"))
            assert user is not None
            alice_id = user.id
            created_ids: list[str] = []
            for idx, (sym, name) in enumerate([("AI.PA", "Air Liquide"), ("MC.PA", "LVMH"), ("TTE.PA", "TotalEnergies")]):
                it = FinanceWatchlistItem(
                    user_id=user.id,
                    list_id=list_id,
                    symbol=sym,
                    yahoo_symbol=sym,
                    eod_ticker=sym,
                    name=name,
                    exchange="PA",
                    currency="EUR",
                    position=idx,
                )
                db.add(it)
                db.flush()
                created_ids.append(it.id)
            db.commit()

        # Réordonner : [TTE.PA, AI.PA, MC.PA]
        new_order = [created_ids[2], created_ids[0], created_ids[1]]
        reord = alice.patch(f"/api/finance/watchlists/{list_id}/reorder", json={"item_ids": new_order})
        assert reord.status_code == 200
        assert reord.json()["item_ids"] == new_order

        # Relire via GET /api/finance/watchlist?include_quotes=false
        fetched = alice.get(f"/api/finance/watchlist?list_id={list_id}&include_quotes=false")
        assert fetched.status_code == 200
        symbols = [it["symbol"] for it in fetched.json()["items"]]
        assert symbols == ["TTE.PA", "AI.PA", "MC.PA"]

        # Vérifier la synchronisation miroir dans finance_warehouse.db
        wh = load_user_watchlists_from_warehouse(warehouse_db_path(settings), alice_id)
        wh_items = sorted(
            [it for it in wh["items"] if it["list_id"] == list_id],
            key=lambda x: x["position"],
        )
        assert [it["symbol"] for it in wh_items] == ["TTE.PA", "AI.PA", "MC.PA"]

        # ID inconnu -> 400
        bad = alice.patch(f"/api/finance/watchlists/{list_id}/reorder", json={"item_ids": ["non-existent-id"]})
        assert bad.status_code == 400

    # Isolation multi-utilisateur : bob ne peut pas réordonner la liste d'alice -> 404
    with _auth_client(app, origin, "bob") as bob:
        forbidden = bob.patch(f"/api/finance/watchlists/{list_id}/reorder", json={"item_ids": new_order})
        assert forbidden.status_code == 404
