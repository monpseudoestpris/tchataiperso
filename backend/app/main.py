import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.orm import sessionmaker

from .config import Settings
from .deps import check_model, claim, current_user, get_conversation, require_admin
from .models import Base, User
from .routers import (
    admin,
    attachments,
    auth,
    blogs,
    conversations,
    family,
    images,
    memories,
    messages,
    skills,
    system,
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
        if "theme" not in conv_columns or "keywords" not in conv_columns:
            with engine.begin() as conn:
                if "theme" not in conv_columns:
                    conn.execute(text("ALTER TABLE conversations ADD COLUMN theme VARCHAR(80) NOT NULL DEFAULT ''"))
                if "keywords" not in conv_columns:
                    conn.execute(text("ALTER TABLE conversations ADD COLUMN keywords JSON NOT NULL DEFAULT '[]'"))
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "family_group_id" not in user_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN family_group_id VARCHAR(36)"))
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
        yield
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
    app.include_router(blogs.router)

    return app


app = create_app()
