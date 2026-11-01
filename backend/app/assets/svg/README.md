# Banques vectorielles locales cLAIr Pages

Ce répertoire stocke les collections locales de graphiques vectoriels utilisés par cLAIr Pages :
- `tabler/` : ~5 200 icônes vectorielles issues de [Tabler Icons](https://tabler.io/icons) (Licence MIT).
- `undraw/` : ~1 700 illustrations didactiques issues de [unDraw](https://undraw.co) (Licence MIT / Open source).

Ces dossiers sont ignorés par Git pour préserver la légèreté du dépôt.
Ils sont téléchargés et initialisés automatiquement via :
```bash
python3 scripts/download_svg_assets.py
```
ou automatiquement lors de l'installation `./scripts/install.sh`.

