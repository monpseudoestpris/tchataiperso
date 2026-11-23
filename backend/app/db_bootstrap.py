"""Bootstrap DDL idempotent de la base applicative (OWD-2).

Ce module isole la logique de vérification/migration incrémentale au démarrage
de l'application (SQLite local et PostgreSQL) hors de `main.py`, avant une
convergence ultérieure vers Alembic seul.
"""

from __future__ import annotations

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from .base_prompt import BASE_USER_PROMPT
from .config import Settings
from .models import Base, User


def bootstrap_database(engine: Engine, sessions: sessionmaker, settings: Settings) -> None:
    """Crée les tables manquantes, applique les ajouts de colonnes idempotents et vérifie les invariants."""
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    if "extraction" not in {column["name"] for column in inspector.get_columns("attachments")}:
        raise RuntimeError(
            "Base non migrée ; exécutez `python -m app.cli migrate-legacy` pour appliquer la migration des pièces jointes."
        )

    conv_columns = {column["name"] for column in inspector.get_columns("conversations")}
    with engine.begin() as conn:
        if "theme" not in conv_columns:
            conn.execute(text("ALTER TABLE conversations ADD COLUMN theme VARCHAR(80) NOT NULL DEFAULT ''"))
        if "keywords" not in conv_columns:
            conn.execute(text("ALTER TABLE conversations ADD COLUMN keywords JSON NOT NULL DEFAULT '[]'"))
        if "topic_space_id" not in conv_columns:
            conn.execute(text("ALTER TABLE conversations ADD COLUMN topic_space_id VARCHAR(36)"))
        if "creativity" not in conv_columns:
            conn.execute(text("ALTER TABLE conversations ADD COLUMN creativity FLOAT"))
        if "sampling_params" not in conv_columns:
            conn.execute(text("ALTER TABLE conversations ADD COLUMN sampling_params JSON"))

    table_names = set(inspector.get_table_names())

    if "skills" in table_names:
        skill_columns = {column["name"] for column in inspector.get_columns("skills")}
        with engine.begin() as conn:
            if "creativity" not in skill_columns:
                conn.execute(text("ALTER TABLE skills ADD COLUMN creativity FLOAT"))
            if "sampling_params" not in skill_columns:
                conn.execute(text("ALTER TABLE skills ADD COLUMN sampling_params JSON"))

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    with engine.begin() as conn:
        if "family_group_id" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN family_group_id VARCHAR(36)"))
        if "system_prompt" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN system_prompt TEXT NOT NULL DEFAULT ''"))
        if "prompt_cache_enabled" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN prompt_cache_enabled BOOLEAN NOT NULL DEFAULT TRUE"))
        if "auto_memory_enabled" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN auto_memory_enabled BOOLEAN NOT NULL DEFAULT TRUE"))
        if "default_voice" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN default_voice VARCHAR(40)"))
        conn.execute(
            text("UPDATE users SET system_prompt = :prompt WHERE system_prompt = '' OR system_prompt IS NULL"),
            {"prompt": BASE_USER_PROMPT},
        )
        # Nettoyage des anciennes consignes de questions finales automatiques dans users.system_prompt
        # (les relances sont désormais pilotées par le toggle du tchat, désactivé par défaut)
        conn.execute(
            text(
                "UPDATE users SET system_prompt = REPLACE("
                "system_prompt, "
                "'Évite les répétitions, introductions artificielles et questions finales automatiques.', "
                "'Évite les répétitions et les introductions artificielles.'"
                ") WHERE system_prompt LIKE '%questions finales automatiques%'"
            )
        )
        conn.execute(
            text(
                "UPDATE users SET system_prompt = REPLACE("
                "system_prompt, "
                "' À la fin de chaque réponse, propose 2 à 3 questions connexes pertinentes pour continuer la discussion.', "
                "''"
                ") WHERE system_prompt LIKE '%2 à 3 questions connexes pertinentes%'"
            )
        )
        conn.execute(
            text(
                "UPDATE users SET system_prompt = REPLACE("
                "system_prompt, "
                "' À la fin de chaque réponse, propose au moins 5 pistes de relance pertinentes (questions, affirmations ou réponses courtes en lien avec ton message) pour continuer la discussion.', "
                "''"
                ") WHERE system_prompt LIKE '%au moins 5 pistes de relance pertinentes%'"
            )
        )

    if "generated_sounds" in table_names:
        sound_columns = {column["name"] for column in inspector.get_columns("generated_sounds")}
        with engine.begin() as conn:
            if "sound_type" not in sound_columns:
                conn.execute(
                    text("ALTER TABLE generated_sounds ADD COLUMN sound_type VARCHAR(30) NOT NULL DEFAULT 'sound_effect'")
                )
            if "instrumental" not in sound_columns:
                conn.execute(text("ALTER TABLE generated_sounds ADD COLUMN instrumental BOOLEAN"))
            if "model_id" not in sound_columns:
                conn.execute(text("ALTER TABLE generated_sounds ADD COLUMN model_id VARCHAR(50)"))

    if "blogs" in table_names:
        blog_columns = {column["name"] for column in inspector.get_columns("blogs")}
        with engine.begin() as conn:
            if "categories" not in blog_columns:
                conn.execute(text("ALTER TABLE blogs ADD COLUMN categories JSON NOT NULL DEFAULT '[\"news\"]'"))

    if "web_pages" in table_names:
        wp_columns = {column["name"] for column in inspector.get_columns("web_pages")}
        with engine.begin() as conn:
            if "kind" not in wp_columns:
                conn.execute(text("ALTER TABLE web_pages ADD COLUMN kind VARCHAR(20) NOT NULL DEFAULT 'page'"))
            if "bricks" not in wp_columns:
                conn.execute(text("ALTER TABLE web_pages ADD COLUMN bricks JSON NOT NULL DEFAULT '[]'"))

    if "web_page_versions" in table_names:
        wpv_columns = {column["name"] for column in inspector.get_columns("web_page_versions")}
        with engine.begin() as conn:
            if "canvas_files" not in wpv_columns:
                conn.execute(text("ALTER TABLE web_page_versions ADD COLUMN canvas_files JSON NOT NULL DEFAULT '[]'"))

    if "finance_quarterly_reports" in table_names:
        fqr_columns = {column["name"] for column in inspector.get_columns("finance_quarterly_reports")}
        dt_type = "TIMESTAMPTZ" if engine.dialect.name == "postgresql" else "DATETIME"
        with engine.begin() as conn:
            if "extracted_tables" not in fqr_columns:
                conn.execute(text("ALTER TABLE finance_quarterly_reports ADD COLUMN extracted_tables JSON"))
            if "extracted_at" not in fqr_columns:
                conn.execute(text(f"ALTER TABLE finance_quarterly_reports ADD COLUMN extracted_at {dt_type}"))

    if "visual_documents" in table_names:
        vdoc_columns = {column["name"] for column in inspector.get_columns("visual_documents")}
        with engine.begin() as conn:
            if "doc_category" not in vdoc_columns:
                conn.execute(
                    text("ALTER TABLE visual_documents ADD COLUMN doc_category VARCHAR(40) NOT NULL DEFAULT 'general'")
                )
                conn.execute(
                    text(
                        "UPDATE visual_documents SET doc_category = 'financial' "
                        "WHERE doc_category = 'general' AND (ocr_model = 'finance-report' OR source_type = 'finance')"
                    )
                )
                conn.execute(
                    text(
                        "UPDATE visual_documents SET doc_category = 'boardgame' "
                        "WHERE doc_category = 'general' AND ("
                        "LOWER(title) LIKE '%regle%' OR LOWER(title) LIKE '%règle%' OR LOWER(title) LIKE '%rule%'"
                        ")"
                    )
                )
            if "external_links" not in vdoc_columns:
                conn.execute(
                    text("ALTER TABLE visual_documents ADD COLUMN external_links JSON NOT NULL DEFAULT '[]'")
                )

    if "finance_watchlist_items" in table_names:
        wl_columns = {column["name"] for column in inspector.get_columns("finance_watchlist_items")}
        wl_uqs = {
            u["name"]: u.get("column_names") or []
            for u in inspector.get_unique_constraints("finance_watchlist_items")
            if u.get("name")
        }
        wl_idxs = {
            idx["name"]: idx.get("column_names") or []
            for idx in inspector.get_indexes("finance_watchlist_items")
            if idx.get("name") and idx.get("unique")
        }
        has_old_user_sym_uq = (
            "uq_finance_watchlist_user_symbol" in wl_uqs
            or any(cols == ["user_id", "symbol"] for cols in wl_uqs.values())
            or any(cols == ["user_id", "symbol"] for cols in wl_idxs.values())
        )
        with engine.begin() as conn:
            if "list_id" not in wl_columns:
                conn.execute(text("ALTER TABLE finance_watchlist_items ADD COLUMN list_id VARCHAR(36)"))
                conn.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_finance_watchlist_items_list_id ON finance_watchlist_items (list_id)")
                )
            if "note" not in wl_columns:
                conn.execute(text("ALTER TABLE finance_watchlist_items ADD COLUMN note VARCHAR(240) NOT NULL DEFAULT ''"))
            if has_old_user_sym_uq:
                if settings.db_url.startswith("sqlite"):
                    # SQLite ne permet pas DROP CONSTRAINT : reconstruire la table proprement en gardant les lignes
                    conn.execute(
                        text(
                            """
                            CREATE TABLE finance_watchlist_items_new (
                                id VARCHAR(36) PRIMARY KEY,
                                user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                                list_id VARCHAR(36) REFERENCES finance_watchlists(id) ON DELETE CASCADE,
                                symbol VARCHAR(32) NOT NULL,
                                yahoo_symbol VARCHAR(32) NOT NULL DEFAULT '',
                                eod_ticker VARCHAR(32) NOT NULL DEFAULT '',
                                name VARCHAR(200) NOT NULL,
                                exchange VARCHAR(80) NOT NULL DEFAULT '',
                                currency VARCHAR(16) NOT NULL DEFAULT 'EUR',
                                note VARCHAR(240) NOT NULL DEFAULT '',
                                position INTEGER NOT NULL DEFAULT 0,
                                created_at DATETIME NOT NULL,
                                CONSTRAINT uq_finance_watchlist_list_symbol UNIQUE (list_id, symbol)
                            )
                            """
                        )
                    )
                    conn.execute(
                        text(
                            """
                            INSERT INTO finance_watchlist_items_new
                                (id, user_id, list_id, symbol, yahoo_symbol, eod_ticker, name, exchange, currency, note, position, created_at)
                            SELECT id, user_id, list_id, symbol, yahoo_symbol, eod_ticker, name, exchange, currency, COALESCE(note, ''), position, created_at
                            FROM finance_watchlist_items
                            """
                        )
                    )
                    conn.execute(text("DROP TABLE finance_watchlist_items"))
                    conn.execute(text("ALTER TABLE finance_watchlist_items_new RENAME TO finance_watchlist_items"))
                    conn.execute(
                        text("CREATE INDEX IF NOT EXISTS ix_finance_watchlist_items_user_id ON finance_watchlist_items (user_id)")
                    )
                    conn.execute(
                        text("CREATE INDEX IF NOT EXISTS ix_finance_watchlist_items_list_id ON finance_watchlist_items (list_id)")
                    )
                else:
                    for cname, ccols in {**wl_uqs, **wl_idxs}.items():
                        if cname == "uq_finance_watchlist_user_symbol" or ccols == ["user_id", "symbol"]:
                            conn.execute(text(f'ALTER TABLE finance_watchlist_items DROP CONSTRAINT IF EXISTS "{cname}"'))
                            conn.execute(text(f'DROP INDEX IF EXISTS "{cname}"'))
                    conn.execute(
                        text("CREATE UNIQUE INDEX IF NOT EXISTS uq_finance_watchlist_list_symbol ON finance_watchlist_items (list_id, symbol)")
                    )

    for table in ("conversations", "attachments", "memories"):
        if "user_id" not in {column["name"] for column in inspector.get_columns(table)}:
            raise RuntimeError(
                "Base non migrée; exécutez les étapes `migrate-schema`, `create-admin` et `migrate-legacy` du README."
            )
        with sessions() as db:
            missing = db.scalar(text(f"SELECT count(*) FROM {table} WHERE user_id IS NULL"))
        if missing:
            raise RuntimeError(f"{missing} ligne(s) de {table} sans propriétaire; exécutez `migrate-legacy --owner <admin>`. ")

    with sessions() as db:
        if not db.scalar(select(User.id).where(User.is_admin.is_(True), User.active.is_(True))):
            raise RuntimeError("Aucun administrateur actif; exécutez `python -m app.cli create-admin --username <identifiant>`. ")
