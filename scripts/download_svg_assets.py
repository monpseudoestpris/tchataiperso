#!/usr/bin/env python3
"""
Script autonome de téléchargement et d'initialisation des banques vectorielles locales
pour cLAIr Pages (Tabler Icons & unDraw).
Peut être exécuté en standalone ou appelé par scripts/install.sh.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))

from app.svg_assets import ensure_svg_assets

if __name__ == "__main__":
    force_download = "--force" in sys.argv
    print("Vérification des banques vectorielles SVG locales...")
    tabler_count, undraw_count = ensure_svg_assets(force=force_download)
    print(f"Banques prêtes : {tabler_count} icônes Tabler Icons et {undraw_count} scènes unDraw.")

