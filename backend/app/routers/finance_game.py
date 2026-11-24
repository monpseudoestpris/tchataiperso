"""Routeur API FastAPI pour le jeu « Trading Replay » du Mode Finance."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..config import Settings
from ..deps import current_user, get_settings
from ..finance_game import (
    DEFAULT_STARTING_CAPITAL,
    close_round_position,
    finish_round,
    get_game_round,
    get_game_state,
    open_round_position,
    reset_game_profile,
    start_game_round,
    step_round,
)
from ..finance_warehouse import warehouse_db_path
from ..models import User

router = APIRouter()


class StartRoundRequest(BaseModel):
    universe_type: Literal["all", "index", "watchlist", "symbol"] = "all"
    universe_value: str = Field(default="", max_length=64)
    timeframe: Literal["day", "week", "month"] = "day"
    horizon_code: Literal["1w", "1m", "3m", "6m", "1y", "2y", "3y", "5y"] = "3m"
    blind_mode: bool = True


class OpenPositionRequest(BaseModel):
    side: Literal["long", "short"]
    size_pct: float = Field(default=100.0, ge=10.0, le=100.0)
    stop_loss: float | None = Field(default=None, gt=0.0)
    take_profit: float | None = Field(default=None, gt=0.0)


class StepRoundRequest(BaseModel):
    steps: int = Field(default=1, ge=1, le=1500)


class ClosePositionRequest(BaseModel):
    finish_now: bool = False


class ResetProfileRequest(BaseModel):
    starting_capital: float = Field(default=DEFAULT_STARTING_CAPITAL, ge=100.0, le=10_000_000.0)
    clear_history: bool = False


@router.get("/state")
def get_finance_game_state_endpoint(
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    db_path = warehouse_db_path(settings)
    return get_game_state(db_path, user.id)


@router.post("/rounds")
def start_finance_game_round_endpoint(
    body: StartRoundRequest,
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    db_path = warehouse_db_path(settings)
    try:
        return start_game_round(
            db_path,
            user.id,
            universe_type=body.universe_type,
            universe_value=body.universe_value,
            timeframe=body.timeframe,
            horizon_code=body.horizon_code,
            blind_mode=body.blind_mode,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/rounds/{round_id}")
def get_finance_game_round_endpoint(
    round_id: str,
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    db_path = warehouse_db_path(settings)
    try:
        return get_game_round(db_path, user.id, round_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/rounds/{round_id}/position")
def open_finance_game_position_endpoint(
    round_id: str,
    body: OpenPositionRequest,
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    db_path = warehouse_db_path(settings)
    try:
        return open_round_position(
            db_path,
            user.id,
            round_id,
            side=body.side,
            size_pct=body.size_pct,
            stop_loss=body.stop_loss,
            take_profit=body.take_profit,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/rounds/{round_id}/step")
def step_finance_game_round_endpoint(
    round_id: str,
    body: StepRoundRequest,
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    db_path = warehouse_db_path(settings)
    try:
        return step_round(db_path, user.id, round_id, steps=body.steps)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/rounds/{round_id}/close")
def close_finance_game_position_endpoint(
    round_id: str,
    body: ClosePositionRequest,
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    db_path = warehouse_db_path(settings)
    try:
        return close_round_position(db_path, user.id, round_id, finish_now=body.finish_now)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/rounds/{round_id}/finish")
def finish_finance_game_round_endpoint(
    round_id: str,
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    db_path = warehouse_db_path(settings)
    try:
        return finish_round(db_path, user.id, round_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/reset")
def reset_finance_game_endpoint(
    body: ResetProfileRequest,
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    db_path = warehouse_db_path(settings)
    return reset_game_profile(
        db_path,
        user.id,
        starting_capital=body.starting_capital,
        clear_history=body.clear_history,
    )
