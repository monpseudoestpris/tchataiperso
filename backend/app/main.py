import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.orm import sessionmaker

from .base_prompt import BASE_USER_PROMPT
from .config import Settings
from .deps import check_model, claim, current_user, get_conversation, require_admin
from .models import Base, User
from .routers import (
    admin,
    agent_teams,
    attachments,
    auth,
    blogs,
    conversations,
    family,
    finance as finance_router,
    hermes,
    hermes_mcp,
    images,
    memories,
    messages,
    pages,
    settings as settings_router,
    skills,
    sounds,
    system,
    topics,
)
from .serializers import (
    IMAGE_ASPECT_RATIOS,
    MAX_GENERATED_IMAGES,
    MAX_SKILL_COUNT,
    MAX_SKILL_CONTEXT_CHARS,
    attachment_json,
    blog_json,
    blog_post_json,
    conversation_json,
    extract_mentioned_skills,
    generated_image_json,
    message_json,
    skill_json,
    sse,
    stamp,
    user_json,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.models  # Fail early with a useful configuration error.

    upload_dir = settings.app_data_dir.resolve() / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    kwargs = {"connect_args": {"check_same_thread": False, "timeout": 30}} if settings.db_url.startswith("sqlite") else {}
    engine = create_engine(settings.db_url, pool_pre_ping=True, **kwargs)
    if settings.db_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def sqlite_pragmas(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")

    sessions = sessionmaker(engine, expire_on_commit=False)
    locks: dict[str, asyncio.Lock] = {}
    login_failures: dict[str, tuple[int, float]] = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        Base.metadata.create_all(engine)
        inspector = inspect(engine)
        if "extraction" not in {column["name"] for column in inspector.get_columns("attachments")}:
            raise RuntimeError("Base non migrée ; exécutez `python -m app.cli migrate-legacy` pour appliquer la migration des pièces jointes.")
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
        if "skills" in inspector.get_table_names():
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
        if "generated_sounds" in inspector.get_table_names():
            sound_columns = {column["name"] for column in inspector.get_columns("generated_sounds")}
            with engine.begin() as conn:
                if "sound_type" not in sound_columns:
                    conn.execute(text("ALTER TABLE generated_sounds ADD COLUMN sound_type VARCHAR(30) NOT NULL DEFAULT 'sound_effect'"))
                if "instrumental" not in sound_columns:
                    conn.execute(text("ALTER TABLE generated_sounds ADD COLUMN instrumental BOOLEAN"))
                if "model_id" not in sound_columns:
                    conn.execute(text("ALTER TABLE generated_sounds ADD COLUMN model_id VARCHAR(50)"))
        if "blogs" in inspector.get_table_names():
            blog_columns = {column["name"] for column in inspector.get_columns("blogs")}
            with engine.begin() as conn:
                if "categories" not in blog_columns:
                    conn.execute(text("ALTER TABLE blogs ADD COLUMN categories JSON NOT NULL DEFAULT '[\"news\"]'"))
        if "web_pages" in inspector.get_table_names():
            wp_columns = {column["name"] for column in inspector.get_columns("web_pages")}
            with engine.begin() as conn:
                if "kind" not in wp_columns:
                    conn.execute(text("ALTER TABLE web_pages ADD COLUMN kind VARCHAR(20) NOT NULL DEFAULT 'page'"))
                if "bricks" not in wp_columns:
                    conn.execute(text("ALTER TABLE web_pages ADD COLUMN bricks JSON NOT NULL DEFAULT '[]'"))
        if "web_page_versions" in inspector.get_table_names():
            wpv_columns = {column["name"] for column in inspector.get_columns("web_page_versions")}
            with engine.begin() as conn:
                if "canvas_files" not in wpv_columns:
                    conn.execute(text("ALTER TABLE web_page_versions ADD COLUMN canvas_files JSON NOT NULL DEFAULT '[]'"))
        if "finance_watchlist_items" in inspector.get_table_names():
            wl_columns = {column["name"] for column in inspector.get_columns("finance_watchlist_items")}
            wl_uqs = {u["name"]: u.get("column_names") or [] for u in inspector.get_unique_constraints("finance_watchlist_items") if u.get("name")}
            wl_idxs = {idx["name"]: idx.get("column_names") or [] for idx in inspector.get_indexes("finance_watchlist_items") if idx.get("name") and idx.get("unique")}
            has_old_user_sym_uq = (
                "uq_finance_watchlist_user_symbol" in wl_uqs
                or any(cols == ["user_id", "symbol"] for cols in wl_uqs.values())
                or any(cols == ["user_id", "symbol"] for cols in wl_idxs.values())
            )
            with engine.begin() as conn:
                if "list_id" not in wl_columns:
                    conn.execute(text("ALTER TABLE finance_watchlist_items ADD COLUMN list_id VARCHAR(36)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_finance_watchlist_items_list_id ON finance_watchlist_items (list_id)"))
                if "note" not in wl_columns:
                    conn.execute(text("ALTER TABLE finance_watchlist_items ADD COLUMN note VARCHAR(240) NOT NULL DEFAULT ''"))
                if has_old_user_sym_uq:
                    if settings.db_url.startswith("sqlite"):
                        # SQLite ne permet pas DROP CONSTRAINT : reconstruire la table proprement en gardant les lignes
                        conn.execute(text(
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
                        ))
                        conn.execute(text(
                            """
                            INSERT INTO finance_watchlist_items_new
                                (id, user_id, list_id, symbol, yahoo_symbol, eod_ticker, name, exchange, currency, note, position, created_at)
                            SELECT id, user_id, list_id, symbol, yahoo_symbol, eod_ticker, name, exchange, currency, COALESCE(note, ''), position, created_at
                            FROM finance_watchlist_items
                            """
                        ))
                        conn.execute(text("DROP TABLE finance_watchlist_items"))
                        conn.execute(text("ALTER TABLE finance_watchlist_items_new RENAME TO finance_watchlist_items"))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_finance_watchlist_items_user_id ON finance_watchlist_items (user_id)"))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_finance_watchlist_items_list_id ON finance_watchlist_items (list_id)"))
                    else:
                        for cname, ccols in {**wl_uqs, **wl_idxs}.items():
                            if cname == "uq_finance_watchlist_user_symbol" or ccols == ["user_id", "symbol"]:
                                conn.execute(text(f'ALTER TABLE finance_watchlist_items DROP CONSTRAINT IF EXISTS "{cname}"'))
                                conn.execute(text(f'DROP INDEX IF EXISTS "{cname}"'))
                        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_finance_watchlist_list_symbol ON finance_watchlist_items (list_id, symbol)"))
        for table in ("conversations", "attachments", "memories"):
            if "user_id" not in {column["name"] for column in inspector.get_columns(table)}:
                raise RuntimeError("Base non migrée; exécutez les étapes `migrate-schema`, `create-admin` et `migrate-legacy` du README.")
            with sessions() as db:
                missing = db.scalar(text(f"SELECT count(*) FROM {table} WHERE user_id IS NULL"))
            if missing:
                raise RuntimeError(f"{missing} ligne(s) de {table} sans propriétaire; exécutez `migrate-legacy --owner <admin>`. ")
        with sessions() as db:
            if not db.scalar(select(User.id).where(User.is_admin.is_(True), User.active.is_(True))):
                raise RuntimeError("Aucun administrateur actif; exécutez `python -m app.cli create-admin --username <identifiant>`. ")
        sync_task: asyncio.Task[None] | None = None
        if (
            not settings.demo_mode
            and settings.finance_exchange_auto_sync_enabled
            and settings.enabled(settings.eod_historical_data_key)
        ):
            from .finance_funds import run_daily_exchange_catalog_sync_loop

            sync_task = asyncio.create_task(run_daily_exchange_catalog_sync_loop(settings))
        try:
            yield
        finally:
            if sync_task is not None:
                sync_task.cancel()
                with suppress(asyncio.CancelledError):
                    await sync_task
            engine.dispose()

    app = FastAPI(title="cLAIr", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.sessions = sessions
    app.state.engine = engine
    app.state.locks = locks
    app.state.login_failures = login_failures
    app.state.upload_dir = upload_dir

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def check_request_origin(request: Request, call_next):
        settings.refresh_from_env_file()
        if request.url.path == "/api/hermes/mcp" or request.url.path.startswith("/api/hermes/mcp/"):
            return await call_next(request)
        origin = request.headers.get("origin")
        if request.method in {"POST", "PATCH", "DELETE"} and origin not in settings.origins:
            return JSONResponse({"detail": "Origine de requête refusée"}, status_code=403)
        return await call_next(request)

    # Enregistrement modulaire des routeurs d'API
    app.include_router(system.router)
    app.include_router(auth.router)
    app.include_router(family.router)
    app.include_router(admin.router)
    app.include_router(conversations.router)
    app.include_router(messages.router)
    app.include_router(skills.router)
    app.include_router(memories.router)
    app.include_router(attachments.router)
    app.include_router(images.router)
    app.include_router(sounds.router)
    app.include_router(blogs.router)
    app.include_router(settings_router.router)
    app.include_router(agent_teams.router)
    app.include_router(topics.router)
    app.include_router(pages.router)
    app.include_router(hermes.router)
    app.include_router(hermes_mcp.router)
    app.include_router(finance_router.router, prefix="/api/finance", tags=["finance"])

    return app


app = create_app()
