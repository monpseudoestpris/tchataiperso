"""Plages d'affichage de la courbe de cours (mapping vers les paramètres Yahoo Finance)."""

from typing import Literal

ChartRange = Literal["1d", "1w", "1m", "3m", "6m", "1y", "2y", "5y", "max"]

DEFAULT_CHART_RANGE: ChartRange = "1m"

# plage -> (paramètre `range` Yahoo, paramètre `interval` Yahoo, intraday ?)
CHART_RANGES: dict[str, tuple[str, str, bool]] = {
    "1d": ("1d", "5m", True),
    "1w": ("5d", "30m", True),
    "1m": ("1mo", "1d", False),
    "3m": ("3mo", "1d", False),
    "6m": ("6mo", "1d", False),
    "1y": ("1y", "1d", False),
    "2y": ("2y", "1d", False),
    "5y": ("5y", "1wk", False),
    "max": ("max", "1mo", False),
}
