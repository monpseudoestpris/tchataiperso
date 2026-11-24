import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from .config import Settings
from .db_bootstrap import bootstrap_database
from .deps import check_model, claim, current_user, get_conversation, require_admin
from .finance_eodhd_usage import configure_usage_db
from .finance_funds import configure_sync_state_db, stop_active_sync_task
from .finance_warehouse import checkpoint_warehouse, warehouse_db_path
from .routers import (
    admin,
    agent_teams,
    attachments,
    auth,
    blogs,
    conversations,
    family,
    finance as finance_router,
    finance_game as finance_game_router,
    hermes,
    hermes_mcp,
    images,
    memories,
    messages,
    pages,
    research_reports,
    settings as settings_router,
    skills,
    sounds,
    system,
    topics,
    videos,
    visual_docs,
    voice,
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
        bootstrap_database(engine, sessions, settings)
        fin_db_path = warehouse_db_path(settings)
        configure_usage_db(fin_db_path)
        configure_sync_state_db(fin_db_path)
        sync_task: asyncio.Task[None] | None = None
        if (
            not settings.demo_mode
            and settings.finance_exchange_auto_sync_enabled
        ):
            from .finance_funds import run_daily_exchange_catalog_sync_loop

            sync_task = asyncio.create_task(run_daily_exchange_catalog_sync_loop(settings))
            _app.state.sync_task = sync_task
        try:
            yield
        finally:
            if sync_task is not None:
                sync_task.cancel()
                with suppress(asyncio.CancelledError):
                    await sync_task
            with suppress(Exception):
                await stop_active_sync_task(timeout_seconds=8.0)
            with suppress(Exception):
                checkpoint_warehouse(fin_db_path)
            configure_usage_db(None)
            configure_sync_state_db(None)
            engine.dispose()

    app = FastAPI(title="cLAIr", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.sessions = sessions
    app.state.engine = engine
    app.state.locks = locks
    app.state.login_failures = login_failures
    app.state.upload_dir = upload_dir
    app.state.shutting_down = False
    app.state.sync_task = None

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
        if (
            getattr(app.state, "shutting_down", False)
            and request.method in {"POST", "PATCH", "DELETE"}
            and request.url.path not in {"/api/system/prepare-shutdown", "/api/system/resume", "/api/auth/logout"}
        ):
            return JSONResponse(
                {"detail": "Arrêt propre en cours : les nouvelles écritures sont gelées pour protéger les bases de données."},
                status_code=503,
            )
        return await call_next(request)

    # Enregistrement modulaire des routeurs d'API
    app.include_router(system.router)
    app.include_router(auth.router)
    app.include_router(family.router)
    app.include_router(admin.router)
    app.include_router(conversations.router)
    app.include_router(messages.router)
    app.include_router(research_reports.router)
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
    app.include_router(videos.router)
    app.include_router(visual_docs.router)
    app.include_router(voice.router)
    app.include_router(finance_router.router, prefix="/api/finance", tags=["finance"])
    app.include_router(finance_game_router.router, prefix="/api/finance/game", tags=["finance-game"])

    return app


app = create_app()
