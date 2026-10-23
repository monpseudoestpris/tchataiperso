import asyncio
import json
import logging
import re
import unicodedata
from contextlib import asynccontextmanager
from datetime import timedelta, timezone
from pathlib import Path
from time import monotonic
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy import create_engine, event, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from . import providers
from .auth import hash_password, new_token, token_digest, verify_password
from .config import Settings
from .context import build_context
from .blog import generate_blog_edition, parse_cards_from_content
from .documents import extract_document, extraction_text
from .models import Attachment, AuthSession, Base, Blog, BlogPost, Conversation, ConversationSkill, GeneratedImage, Invitation, Memory, Message, Skill, User, now
from .schemas import (AcceptInvitation, AdminUpdateUser, ClassifyConversationRequest, CONVERSATION_THEMES,
                      CreateBlog, CreateConversation, CreateImage, CreateMemory, CreateSkill, FetchUrlRequest,
                      ImproveImagePrompt, ImproveSkillPrompt, LoginRequest, SendMessage, SetConversationSkills,
                      UpdateBlog, UpdateConversation, UpdateSkill)
from .web import fetch_and_parse_web_url


MAX_SKILL_COUNT = 100
MAX_SKILL_CONTEXT_CHARS = 12000
MAX_GENERATED_IMAGES = 200
IMAGE_ASPECT_RATIOS = {"1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"}
_DEFAULT_STREAM_CHAT = providers.stream_chat
_DEFAULT_CLASSIFY_CONVERSATION = providers.classify_conversation
_DEFAULT_REWRITE_SEARCH_QUERY = providers.rewrite_search_query
_logger = logging.getLogger("uvicorn.error")


def stamp(value) -> str:
    return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()


def attachment_json(item: Attachment) -> dict:
    url_source = item.extraction.get("url") if isinstance(item.extraction, dict) else None
    finance_meta = None
    if isinstance(item.extraction, dict) and item.extraction.get("model") in ("yahoo-finance", "eod-historical-data"):
        finance_meta = {
            k: item.extraction.get(k)
            for k in ("symbol", "short_name", "long_name", "price", "currency", "change_percent", "exchange", "url",
                      "provider", "source_label")
            if item.extraction.get(k) is not None
        }
    return {"id": item.id, "filename": item.filename, "mime_type": item.mime_type, "size": item.size,
            "url": f"/api/attachments/{item.id}/file", "created_at": stamp(item.created_at),
            "extracted_chars": len(item.extracted_text), "has_extraction": bool(item.extraction),
            "page_count": len(item.extraction["pages"]) if item.extraction and "pages" in item.extraction else 0,
            "source_url": url_source, "finance_meta": finance_meta}


def generated_image_json(item: GeneratedImage) -> dict:
    return {"id": item.id, "prompt": item.prompt, "aspect_ratio": item.aspect_ratio,
            "filename": item.filename, "mime_type": item.mime_type, "size": item.size,
            "url": f"/api/images/{item.id}/file", "download_url": f"/api/images/{item.id}/file?download=1",
            "created_at": stamp(item.created_at)}


def message_json(item: Message) -> dict:
    return {"id": item.id, "role": item.role, "content": item.content, "created_at": stamp(item.created_at),
            "attachments": [attachment_json(value) for value in item.attachments], "sources": item.sources}


def skill_json(item: Skill) -> dict:
    return {"id": item.id, "name": item.name, "prompt": item.prompt,
            "created_at": stamp(item.created_at), "updated_at": stamp(item.updated_at)}


def blog_post_json(item: BlogPost) -> dict:
    cards = parse_cards_from_content(item.content)
    return {
        "id": item.id,
        "blog_id": item.blog_id,
        "title": item.title,
        "summary": item.summary,
        "content": item.content,
        "cards": cards,
        "sources": item.sources or [],
        "created_at": stamp(item.created_at),
    }


def blog_json(item: Blog, include_posts: bool = False) -> dict:
    posts = item.posts or []
    latest = posts[0] if posts else None
    result = {
        "id": item.id,
        "title": item.title,
        "prompt": item.prompt,
        "auto_refresh": item.auto_refresh,
        "theme": getattr(item, "theme", None) or "sunset",
        "created_at": stamp(item.created_at),
        "updated_at": stamp(item.updated_at),
        "posts_count": len(posts),
        "latest_post": {
            "id": latest.id,
            "title": latest.title,
            "summary": latest.summary,
            "created_at": stamp(latest.created_at),
        } if latest else None,
    }
    if include_posts:
        result["posts"] = [blog_post_json(p) for p in posts]
    return result



def conversation_json(item: Conversation, detail: bool = False) -> dict:
    raw_keywords = item.keywords if isinstance(item.keywords, list) else []
    keywords = [str(k).strip() for k in raw_keywords if isinstance(k, str) and str(k).strip()][:5]
    result = {
        "id": item.id,
        "title": item.title,
        "model": item.model,
        "theme": (item.theme or "").strip(),
        "keywords": keywords,
        "created_at": stamp(item.created_at),
        "updated_at": stamp(item.updated_at),
        "summary": item.summary,
    }
    if detail:
        result["messages"] = [message_json(message) for message in item.messages]
        result["skills"] = [skill_json(link.skill) for link in item.skill_links]
    return result


def sse(name: str, value: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(value, ensure_ascii=False)}\n\n"


def extract_mentioned_skills(content: str, user_skills: list[Skill]) -> list[Skill]:
    """Finds user skills mentioned in the content via @slug or @name (e.g. @prof, @feynman)."""
    raw_tags = re.findall(r"@([a-zA-Z0-9_\u00C0-\u017F-]+)", content)
    if not raw_tags or not user_skills:
        return []
    resolved: list[Skill] = []
    for tag in raw_tags:
        tag_norm = unicodedata.normalize("NFKD", tag).encode("ascii", "ignore").decode("ascii").lower().strip("-_")
        if not tag_norm:
            continue
        for skill in user_skills:
            if skill in resolved:
                continue
            skill_norm = unicodedata.normalize("NFKD", skill.name).encode("ascii", "ignore").decode("ascii").lower().strip()
            skill_slug = re.sub(r"[^a-z0-9]+", "-", skill_norm).strip("-")
            skill_words = [w for w in re.split(r"[^a-z0-9]+", skill_norm) if w]
            matches = (
                tag_norm == skill_slug
                or tag_norm in skill_words
                or skill_slug.startswith(tag_norm)
                or any(w.startswith(tag_norm) for w in skill_words)
                or (len(skill_slug) >= 3 and tag_norm.startswith(skill_slug))
                or (len(tag_norm) >= 3 and tag_norm in skill_slug)
            )
            if matches:
                resolved.append(skill)
    return resolved


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    models = settings.models  # Fail early with a useful configuration error.
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
    async def lifespan(_app):
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
    app.state.settings, app.state.sessions, app.state.engine = settings, sessions, engine
    app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type"])

    @app.middleware("http")
    async def check_request_origin(request: Request, call_next):
        settings.refresh_from_env_file()
        origin = request.headers.get("origin")
        if request.method in {"POST", "PATCH", "DELETE"} and origin not in settings.origins:
            return JSONResponse({"detail": "Origine de requête refusée"}, status_code=403)
        return await call_next(request)

    def get_conversation(db: Session, conversation_id: str, user_id: str) -> Conversation:
        item = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id))
        if not item:
            raise HTTPException(404, "Conversation introuvable")
        return item

    def check_model(model: str) -> dict:
        found = next((item for item in settings.models if item["id"] == model), None)
        if not found:
            raise HTTPException(422, "Modèle absent de LLM_MODELS")
        return found

    def claim(user_id: str, conversation_id: str) -> asyncio.Lock:
        lock = locks.setdefault(f"{user_id}:{conversation_id}", asyncio.Lock())
        if lock.locked():
            raise HTTPException(409, "Une réponse est déjà en cours dans cette conversation")
        return lock

    def current_user(request: Request) -> User:
        token = request.cookies.get(settings.session_cookie_name)
        if not token:
            raise HTTPException(401, "Connexion requise")
        with sessions() as db:
            auth_session = db.scalar(select(AuthSession).where(
                AuthSession.token_hash == token_digest(token), AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now()))
            user = db.get(User, auth_session.user_id) if auth_session else None
            if not user or not user.active:
                raise HTTPException(401, "Session invalide ou expirée")
            return user

    def user_json(user: User) -> dict:
        return {"id": user.id, "username": user.username, "is_admin": user.is_admin}

    def require_admin(user: User = Depends(current_user)) -> User:
        if not user.is_admin:
            raise HTTPException(403, "Accès réservé à l’administration")
        return user

    @app.post("/api/auth/login")
    def login(body: LoginRequest, request: Request, response: Response):
        current_time = monotonic()
        if len(login_failures) > 1024:
            for address, (_, started_at) in list(login_failures.items()):
                if current_time - started_at >= 60:
                    login_failures.pop(address, None)
        address = request.client.host if request.client else "unknown"
        attempts, window_start = login_failures.get(address, (0, current_time))
        if current_time - window_start >= 60:
            attempts, window_start = 0, current_time
        if attempts >= 10:
            raise HTTPException(429, "Trop de tentatives. Réessayez dans une minute.")
        with sessions() as db:
            user = db.scalar(select(User).where(User.username == body.username, User.active.is_(True)))
            if not user or not verify_password(body.password, user.password_hash):
                login_failures[address] = (attempts + 1, window_start)
                raise HTTPException(401, "Identifiant ou mot de passe incorrect")
            login_failures.pop(address, None)
            token = new_token()
            expires_at = now() + timedelta(days=settings.session_days)
            db.add(AuthSession(user_id=user.id, token_hash=token_digest(token), expires_at=expires_at))
            db.commit()
            result = user_json(user)
        response.set_cookie(settings.session_cookie_name, token, max_age=settings.session_days * 86400,
                            httponly=True, secure=settings.session_cookie_secure, samesite="lax", path="/")
        return result

    @app.get("/api/auth/session")
    def session_info(user: User = Depends(current_user)):
        return user_json(user)

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response, user: User = Depends(current_user)):
        token = request.cookies.get(settings.session_cookie_name)
        with sessions() as db:
            auth_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(token)))
            if auth_session and not auth_session.revoked_at:
                auth_session.revoked_at = now()
                db.commit()
        response.delete_cookie(settings.session_cookie_name, path="/", httponly=True,
                               secure=settings.session_cookie_secure, samesite="lax")
        response.status_code = 204
        return response

    @app.post("/api/auth/register", status_code=201)
    def accept_invitation(body: AcceptInvitation):
        with sessions() as db:
            invitation = db.scalar(select(Invitation).where(
                Invitation.token_hash == token_digest(body.token), Invitation.used_at.is_(None),
                Invitation.expires_at > now()).with_for_update())
            if not invitation:
                raise HTTPException(400, "Invitation invalide, expirée ou déjà utilisée")
            user = User(username=body.username, password_hash=hash_password(body.password), is_admin=False)
            invitation.used_at = now()
            db.add(user)
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise HTTPException(409, "Cet identifiant est déjà utilisé") from exc
            return user_json(user)

    @app.get("/api/admin/users")
    def list_users(_admin: User = Depends(require_admin)):
        with sessions() as db:
            return [{"id": item.id, "username": item.username, "is_admin": item.is_admin,
                     "active": item.active, "created_at": stamp(item.created_at)}
                    for item in db.scalars(select(User).order_by(User.created_at))]

    @app.post("/api/admin/invitations", status_code=201)
    def create_invitation(admin: User = Depends(require_admin)):
        token = new_token()
        expires_at = now() + timedelta(days=settings.invitation_days)
        with sessions() as db:
            db.add(Invitation(created_by_user_id=admin.id, token_hash=token_digest(token), expires_at=expires_at))
            db.commit()
        return {"token": token, "expires_at": stamp(expires_at)}

    @app.patch("/api/admin/users/{user_id}")
    def update_user(user_id: str, body: AdminUpdateUser, admin: User = Depends(require_admin)):
        with sessions() as db:
            target = db.get(User, user_id)
            if not target:
                raise HTTPException(404, "Utilisateur introuvable")
            if target.id == admin.id and not body.active:
                raise HTTPException(409, "Vous ne pouvez pas désactiver votre propre compte")
            if target.is_admin and target.active and not body.active:
                active_admins = db.scalar(select(func.count()).select_from(User).where(
                    User.is_admin.is_(True), User.active.is_(True)))
                if active_admins <= 1:
                    raise HTTPException(409, "Le dernier administrateur actif ne peut pas être désactivé")
            target.active = body.active
            db.commit()
            return {"id": target.id, "username": target.username, "is_admin": target.is_admin,
                    "active": target.active, "created_at": stamp(target.created_at)}

    @app.get("/api/health")
    def health():
        with sessions() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/api/config")
    def config():
        search_providers = []
        if not settings.demo_mode:
            if settings.searxng_url.strip():
                search_providers.append("searxng")
            if settings.enabled(settings.brave_api_key):
                search_providers.append("brave")
            if settings.duckduckgo_enabled:
                search_providers.append("duckduckgo_instant_answers")
        return {"models": settings.models, "default_model": settings.default_model, "demo_mode": settings.demo_mode,
                "themes": list(CONVERSATION_THEMES),
                "search_providers": search_providers,
                "image_prompt_model": settings.image_prompt_model,
                "image_models": settings.available_image_models,
                "default_image_model": settings.effective_default_image_model,
                "features": {"chat": settings.demo_mode or settings.enabled(settings.llm_api_key),
                             "web_search": settings.web_search_enabled,
                             "ocr": settings.enabled(settings.mistral_api_key),
                             "image_generation": bool(settings.available_image_models)}}

    @app.get("/api/conversations")
    def list_conversations(
        q: str = "",
        theme: str = "",
        keyword: str = "",
        user: User = Depends(current_user),
    ):
        query_norm = q.strip().lstrip("#").casefold()
        theme_norm = theme.strip().casefold()
        keyword_norm = keyword.strip().lstrip("#").casefold()
        with sessions() as db:
            items = list(db.scalars(select(Conversation).where(
                Conversation.user_id == user.id).order_by(Conversation.updated_at.desc())))
            results = []
            for item in items:
                data = conversation_json(item)
                if theme_norm and (data["theme"] or "général").casefold() != theme_norm:
                    continue
                if keyword_norm and not any(keyword_norm in kw.casefold() for kw in data["keywords"]):
                    continue
                if query_norm:
                    haystack = " ".join([
                        data["title"],
                        data["theme"],
                        data["summary"] or "",
                        " ".join(data["keywords"]),
                    ]).casefold()
                    if query_norm not in haystack:
                        continue
                results.append(data)
            return results

    @app.post("/api/conversations", status_code=201)
    def new_conversation(body: CreateConversation, user: User = Depends(current_user)):
        model = body.model or settings.default_model
        check_model(model)
        with sessions() as db:
            item = Conversation(
                user_id=user.id,
                title=body.title.strip() or "Nouvelle conversation",
                model=model,
                theme=(body.theme or "").strip(),
                keywords=[k.strip().lstrip("#") for k in (body.keywords or []) if k.strip()][:5],
            )
            db.add(item)
            db.commit()
            return conversation_json(item, True)

    @app.post("/api/conversations/classify-all")
    async def classify_all_conversations(force: bool = False, user: User = Depends(current_user)):
        with sessions() as db:
            conversations = list(db.scalars(select(Conversation).where(
                Conversation.user_id == user.id).order_by(Conversation.updated_at.desc())))
            targets = []
            for item in conversations:
                if not item.messages:
                    continue
                if force or not item.theme or not item.keywords or item.title == "Nouvelle conversation":
                    user_msgs = "\n".join(m.content for m in item.messages if m.role == "user" and m.content.strip())[:1500]
                    asst_msgs = "\n".join(m.content for m in item.messages if m.role == "assistant" and m.content.strip())[:1500]
                    targets.append((item.id, item.title, user_msgs, asst_msgs))

        use_real = not settings.demo_mode and settings.enabled(settings.llm_api_key)
        updates: dict[str, dict] = {}
        for conv_id, curr_title, user_msgs, asst_msgs in targets:
            if use_real:
                try:
                    meta = await providers.classify_conversation(settings, user_msgs, asst_msgs, current_title=curr_title)
                except providers.ProviderError:
                    meta = providers.fallback_conversation_metadata(user_msgs, asst_msgs, current_title=curr_title)
            else:
                meta = providers.fallback_conversation_metadata(user_msgs, asst_msgs, current_title=curr_title)
            updates[conv_id] = meta

        with sessions() as db:
            for conv_id, meta in updates.items():
                item = db.scalar(select(Conversation).where(Conversation.id == conv_id, Conversation.user_id == user.id))
                if not item:
                    continue
                if (force or item.title == "Nouvelle conversation") and meta.get("title"):
                    item.title = meta["title"][:200]
                if meta.get("theme"):
                    item.theme = meta["theme"][:80]
                if meta.get("keywords"):
                    item.keywords = meta["keywords"][:5]
            db.commit()
            return [conversation_json(item) for item in db.scalars(select(Conversation).where(
                Conversation.user_id == user.id).order_by(Conversation.updated_at.desc()))]

    @app.get("/api/conversations/{conversation_id}")
    def read_conversation(conversation_id: str, user: User = Depends(current_user)):
        with sessions() as db:
            return conversation_json(get_conversation(db, conversation_id, user.id), True)

    @app.post("/api/conversations/{conversation_id}/classify")
    async def classify_single_conversation(
        conversation_id: str,
        body: ClassifyConversationRequest | None = None,
        user: User = Depends(current_user),
    ):
        lock_key = f"{user.id}:{conversation_id}"
        if locks.get(lock_key) and locks[lock_key].locked():
            raise HTTPException(409, "Attendez la fin de la réponse")
        update_title = True if body is None else body.update_title
        with sessions() as db:
            item = get_conversation(db, conversation_id, user.id)
            if not item.messages:
                raise HTTPException(422, "Ajoutez au moins un message avant de générer les mots-clés")
            user_msgs = "\n".join(m.content for m in item.messages if m.role == "user" and m.content.strip())[:1500]
            asst_msgs = "\n".join(m.content for m in item.messages if m.role == "assistant" and m.content.strip())[:1500]
            curr_title = item.title

        if not settings.demo_mode and settings.enabled(settings.llm_api_key):
            try:
                meta = await providers.classify_conversation(settings, user_msgs, asst_msgs, current_title=curr_title)
            except providers.ProviderError:
                meta = providers.fallback_conversation_metadata(user_msgs, asst_msgs, current_title=curr_title)
        else:
            meta = providers.fallback_conversation_metadata(user_msgs, asst_msgs, current_title=curr_title)

        with sessions() as db:
            item = get_conversation(db, conversation_id, user.id)
            if update_title and meta.get("title"):
                item.title = meta["title"][:200]
            if meta.get("theme"):
                item.theme = meta["theme"][:80]
            if meta.get("keywords"):
                item.keywords = meta["keywords"][:5]
            item.updated_at = now()
            db.commit()
            return conversation_json(item, True)

    @app.patch("/api/conversations/{conversation_id}")
    def edit_conversation(conversation_id: str, body: UpdateConversation, user: User = Depends(current_user)):
        lock_key = f"{user.id}:{conversation_id}"
        if locks.get(lock_key) and locks[lock_key].locked():
            raise HTTPException(409, "Attendez la fin de la réponse")
        with sessions() as db:
            item = get_conversation(db, conversation_id, user.id)
            if body.title is not None:
                item.title = body.title.strip() or "Nouvelle conversation"
            if body.model is not None:
                check_model(body.model)
                item.model = body.model
            if body.theme is not None:
                item.theme = body.theme.strip()[:80]
            if body.keywords is not None:
                item.keywords = body.keywords[:5]
            item.updated_at = now()
            db.commit()
            return conversation_json(item, True)

    @app.delete("/api/conversations/{conversation_id}", status_code=204)
    def delete_conversation(conversation_id: str, user: User = Depends(current_user)):
        lock_key = f"{user.id}:{conversation_id}"
        if locks.get(lock_key) and locks[lock_key].locked():
            raise HTTPException(409, "Attendez la fin de la réponse")
        with sessions() as db:
            item = get_conversation(db, conversation_id, user.id)
            files = [attachment for message in item.messages for attachment in message.attachments]
            names = [attachment.storage_name for attachment in files]
            for attachment in files:
                db.delete(attachment)
            db.delete(item)
            db.commit()
        for name in names:
            (upload_dir / name).unlink(missing_ok=True)
        locks.pop(lock_key, None)
        return Response(status_code=204)

    @app.get("/api/memories")
    def list_memories(user: User = Depends(current_user)):
        with sessions() as db:
            return [{"id": item.id, "content": item.content, "created_at": stamp(item.created_at)}
                    for item in db.scalars(select(Memory).where(Memory.user_id == user.id).order_by(Memory.created_at))]

    @app.post("/api/memories", status_code=201)
    def add_memory(body: CreateMemory, user: User = Depends(current_user)):
        if not body.content.strip():
            raise HTTPException(422, "Le souvenir ne peut pas être vide")
        with sessions() as db:
            if len(db.scalars(select(Memory).where(Memory.user_id == user.id)).all()) >= 100:
                raise HTTPException(422, "Limite de 100 souvenirs atteinte")
            item = Memory(user_id=user.id, content=body.content.strip())
            db.add(item)
            db.commit()
            return {"id": item.id, "content": item.content, "created_at": stamp(item.created_at)}

    @app.delete("/api/memories/{memory_id}", status_code=204)
    def delete_memory(memory_id: str, user: User = Depends(current_user)):
        with sessions() as db:
            item = db.scalar(select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id))
            if not item:
                raise HTTPException(404, "Souvenir introuvable")
            db.delete(item)
            db.commit()
        return Response(status_code=204)

    @app.get("/api/skills")
    def list_skills(user: User = Depends(current_user)):
        with sessions() as db:
            return [skill_json(item) for item in db.scalars(
                select(Skill).where(Skill.user_id == user.id).order_by(Skill.created_at, Skill.id))]

    @app.post("/api/skills", status_code=201)
    def create_skill(body: CreateSkill, user: User = Depends(current_user)):
        with sessions() as db:
            count = db.scalar(select(func.count()).select_from(Skill).where(Skill.user_id == user.id))
            if count >= MAX_SKILL_COUNT:
                raise HTTPException(422, f"Limite de {MAX_SKILL_COUNT} compétences atteinte")
            item = Skill(user_id=user.id, name=body.name, prompt=body.prompt)
            db.add(item)
            db.commit()
            return skill_json(item)

    @app.post("/api/skills/improve")
    async def improve_skill(body: ImproveSkillPrompt, user: User = Depends(current_user)):
        if settings.demo_mode or not settings.enabled(settings.llm_api_key):
            raise HTTPException(503, "L'amélioration des compétences nécessite une clé LLM_API_KEY et le mode IA réel")
        try:
            prompt = await providers.improve_skill_prompt(settings, settings.default_model, body.prompt)
        except providers.ProviderError as exc:
            raise HTTPException(502, str(exc)) from exc
        return {"prompt": prompt}

    @app.patch("/api/skills/{skill_id}")
    def update_skill(skill_id: str, body: UpdateSkill, user: User = Depends(current_user)):
        with sessions() as db:
            item = db.scalar(select(Skill).where(Skill.id == skill_id, Skill.user_id == user.id))
            if not item:
                raise HTTPException(404, "Compétence introuvable")
            new_prompt = body.prompt if body.prompt is not None else item.prompt
            for link in item.conversation_links:
                other_prompt_chars = sum(len(active_link.skill.prompt) for active_link in link.conversation.skill_links
                                         if active_link.skill_id != item.id)
                skill_limit = min(MAX_SKILL_CONTEXT_CHARS, settings.max_context_chars - 5000)
                if other_prompt_chars + len(new_prompt) > skill_limit:
                    raise HTTPException(422, "Les prompts actifs de cette conversation dépasseraient la limite de contexte")
            if body.name is not None:
                item.name = body.name
            if body.prompt is not None:
                item.prompt = body.prompt
            item.updated_at = now()
            db.commit()
            return skill_json(item)

    @app.delete("/api/skills/{skill_id}", status_code=204)
    def delete_skill(skill_id: str, user: User = Depends(current_user)):
        with sessions() as db:
            item = db.scalar(select(Skill).where(Skill.id == skill_id, Skill.user_id == user.id))
            if not item:
                raise HTTPException(404, "Compétence introuvable")
            db.delete(item)
            db.commit()
        return Response(status_code=204)

    @app.get("/api/conversations/{conversation_id}/skills")
    def list_conversation_skills(conversation_id: str, user: User = Depends(current_user)):
        with sessions() as db:
            conversation = get_conversation(db, conversation_id, user.id)
            return [skill_json(link.skill) for link in conversation.skill_links]

    @app.patch("/api/conversations/{conversation_id}/skills")
    def set_conversation_skills(conversation_id: str, body: SetConversationSkills, user: User = Depends(current_user)):
        lock_key = f"{user.id}:{conversation_id}"
        if locks.get(lock_key) and locks[lock_key].locked():
            raise HTTPException(409, "Attendez la fin de la réponse")
        with sessions() as db:
            conversation = get_conversation(db, conversation_id, user.id)
            found = list(db.scalars(select(Skill).where(Skill.id.in_(body.skill_ids), Skill.user_id == user.id))) if body.skill_ids else []
            if len(found) != len(body.skill_ids):
                raise HTTPException(404, "Une ou plusieurs compétences sont introuvables")
            by_id = {item.id: item for item in found}
            selected = [by_id[item_id] for item_id in body.skill_ids]
            skill_limit = min(MAX_SKILL_CONTEXT_CHARS, settings.max_context_chars - 5000)
            if sum(len(item.prompt) for item in selected) > skill_limit:
                raise HTTPException(422, "Les prompts actifs dépassent la limite de contexte")
            conversation.skill_links.clear()
            db.flush()
            conversation.skill_links = [ConversationSkill(skill=item, position=index) for index, item in enumerate(selected)]
            conversation.updated_at = now()
            db.commit()
            return [skill_json(item) for item in selected]

    @app.post("/api/attachments", status_code=201)
    async def upload(file: UploadFile = File(...), user: User = Depends(current_user)):
        try:
            content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
        finally:
            await file.close()
        if len(content) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"Fichier limité à {settings.max_upload_mb} Mo")
        if not content:
            raise HTTPException(422, "Fichier vide")
        filename = Path((file.filename or "document").replace("\\", "/")).name[:255]
        try:
            mime, extracted, extraction = await extract_document(settings, content, filename)
        except providers.ProviderError as exc:
            raise HTTPException(502, str(exc)) from exc
        if mime.startswith("image/") and len(content) > 8 * 1024 * 1024:
            raise HTTPException(413, "Les images sont limitées à 8 Mo pour la vision")
        storage_name = str(uuid4())
        path = upload_dir / storage_name
        path.write_bytes(content)
        try:
            with sessions() as db:
                item = Attachment(user_id=user.id, filename=filename, mime_type=mime, size=len(content),
                                  storage_name=storage_name, extracted_text=extracted, extraction=extraction)
                db.add(item)
                db.commit()
                return attachment_json(item)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    @app.post("/api/attachments/url", status_code=201)
    async def upload_url(body: FetchUrlRequest, user: User = Depends(current_user)):
        filename, content, mime, extracted, extraction = await fetch_and_parse_web_url(
            settings, body.url.strip()
        )
        storage_name = str(uuid4())
        path = upload_dir / storage_name
        path.write_bytes(content)
        try:
            with sessions() as db:
                item = Attachment(
                    user_id=user.id,
                    filename=filename,
                    mime_type=mime,
                    size=len(content),
                    storage_name=storage_name,
                    extracted_text=extracted,
                    extraction=extraction,
                )
                db.add(item)
                db.commit()
                return attachment_json(item)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    @app.get("/api/attachments/{attachment_id}/extraction")
    def attachment_extraction(attachment_id: str, user: User = Depends(current_user)):
        with sessions() as db:
            item = db.scalar(select(Attachment).where(Attachment.id == attachment_id, Attachment.user_id == user.id))
            if not item:
                raise HTTPException(404, "Pièce jointe introuvable")
            return JSONResponse({"extraction": item.extraction}, headers={"Cache-Control": "no-store"})

    @app.get("/api/attachments/{attachment_id}/file")
    def attachment_file(attachment_id: str, user: User = Depends(current_user)):
        with sessions() as db:
            item = db.scalar(select(Attachment).where(Attachment.id == attachment_id, Attachment.user_id == user.id))
            if not item or not (upload_dir / item.storage_name).is_file():
                raise HTTPException(404, "Pièce jointe introuvable")
            return FileResponse(upload_dir / item.storage_name, media_type=item.mime_type, filename=item.filename,
                                content_disposition_type="inline" if item.mime_type.startswith("image/") else "attachment",
                                headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})

    @app.delete("/api/attachments/{attachment_id}", status_code=204)
    def delete_unattached_file(attachment_id: str, user: User = Depends(current_user)):
        with sessions() as db:
            item = db.scalar(select(Attachment).where(
                Attachment.id == attachment_id, Attachment.user_id == user.id).with_for_update())
            if not item:
                raise HTTPException(404, "Pièce jointe introuvable")
            if item.message_id:
                raise HTTPException(409, "Cette pièce jointe appartient à un message ; supprimez sa conversation pour la retirer")
            storage_name = item.storage_name
            db.delete(item)
            db.commit()
        (upload_dir / storage_name).unlink(missing_ok=True)
        return Response(status_code=204)

    @app.post("/api/conversations/{conversation_id}/messages")
    async def send_message(conversation_id: str, body: SendMessage, user: User = Depends(current_user)):
        if not settings.demo_mode and not settings.enabled(settings.llm_api_key):
            raise HTTPException(503, "Configurez LLM_API_KEY ou activez explicitement DEMO_MODE pour une simulation")
        if not body.content.strip() and not body.attachment_ids:
            raise HTTPException(422, "Écrivez un message ou joignez un document")
        if (body.web_search or body.deep_search) and not settings.web_search_enabled:
            raise HTTPException(503, "La recherche web nécessite SearXNG, BRAVE_API_KEY ou DUCKDUCKGO_ENABLED en mode IA réel")
        lock = claim(user.id, conversation_id)
        await lock.acquire()
        try:
            with sessions() as db:
                conversation = get_conversation(db, conversation_id, user.id)
                model = body.model or conversation.model
                model_info = check_model(model)
                attachments = []
                for attachment_id in body.attachment_ids:
                    item = db.scalar(select(Attachment).where(
                        Attachment.id == attachment_id, Attachment.user_id == user.id).with_for_update())
                    if not item or item.message_id:
                        raise HTTPException(422, "Pièce jointe introuvable ou déjà utilisée")
                    attachments.append(item)
                if sum(item.mime_type.startswith("image/") for item in attachments) > 4:
                    raise HTTPException(422, "Joignez au maximum 4 images par message pour qu'elles soient toutes analysées")
                for item in attachments:
                    if item.mime_type.startswith("image/") and not item.extracted_text and not model_info["vision"] and not settings.demo_mode:
                        raise HTTPException(422, "Joignez à nouveau cette image pour l'analyser, ou choisissez un modèle vision.")
                message = Message(conversation_id=conversation_id, role="user", content=body.content.strip())
                db.add(message)
                db.flush()
                for item in attachments:
                    item.message_id = message.id

                # Auto-parse any web URLs contained directly in the message text
                raw_urls = re.findall(r'https?://[^\s<>"]+', body.content)
                existing_urls = {
                    att.extraction.get("url")
                    for att in attachments
                    if isinstance(att.extraction, dict) and att.extraction.get("url")
                }
                urls_to_fetch = []
                for u in raw_urls:
                    clean_u = u.rstrip(".,;:!?)'\"")
                    if clean_u and clean_u not in existing_urls and clean_u not in urls_to_fetch:
                        urls_to_fetch.append(clean_u)

                for target_url in urls_to_fetch[:3]:
                    try:
                        u_fn, u_cnt, u_mime, u_txt, u_extr = await fetch_and_parse_web_url(settings, target_url)
                        u_storage = str(uuid4())
                        u_path = upload_dir / u_storage
                        u_path.write_bytes(u_cnt)
                        web_att = Attachment(
                            user_id=user.id,
                            filename=u_fn,
                            mime_type=u_mime,
                            size=len(u_cnt),
                            storage_name=u_storage,
                            extracted_text=u_txt,
                            extraction=u_extr,
                            message_id=message.id,
                        )
                        db.add(web_att)
                        attachments.append(web_att)
                    except Exception as exc:
                        _logger.warning("Échec d'analyse automatique de l'URL %s: %s", target_url, exc)

                # Auto-fetch real-time financial & stock data (EOD Historical Data, Yahoo Finance)
                # In deep_search mode, financial data is only fetched if explicitly requested via finance_mode
                from .finance import process_message_finance_inquiries
                u_skills_pre = list(db.scalars(select(Skill).where(Skill.user_id == user.id)))
                active_skill_prompts = [
                    s.prompt.lower()
                    for s in (extract_mentioned_skills(body.content, u_skills_pre) + [s for s in u_skills_pre if s.id in body.skill_ids])
                ]
                has_finance_skill = any("financ" in p or "bours" in p for p in active_skill_prompts)
                is_finance_active = body.finance_mode or (has_finance_skill and not body.deep_search)
                previous_finance_targets: list[str] = []
                recent_turns: list[dict[str, str]] = []
                for past in conversation.messages:
                    if past.id == message.id:
                        continue
                    recent_turns.append({"role": past.role, "content": past.content})
                    for past_att in past.attachments:
                        ext = past_att.extraction if isinstance(past_att.extraction, dict) else {}
                        if ext.get("model") in ("yahoo-finance", "eod-historical-data") and ext.get("symbol"):
                            sym = str(ext["symbol"])
                            if sym in previous_finance_targets:
                                previous_finance_targets.remove(sym)
                            previous_finance_targets.insert(0, sym)
                entity_resolver = None
                if not settings.demo_mode and settings.enabled(settings.llm_api_key) and not body.deep_search:
                    async def entity_resolver(text: str, previous: list[str]) -> list[str]:
                        return await providers.extract_finance_targets(settings, text, previous, recent_turns[-4:])
                finance_failures: list[str] = []
                try:
                    if not body.deep_search or body.finance_mode:
                        finance_atts = await process_message_finance_inquiries(
                            settings, body.content, attachments, user.id, message.id, upload_dir,
                            finance_mode=is_finance_active,
                            previous_targets=previous_finance_targets,
                            entity_resolver=entity_resolver,
                            failures=finance_failures,
                        )
                        for f_att in finance_atts:
                            db.add(f_att)
                            attachments.append(f_att)
                except Exception as exc:
                    _logger.warning("Échec lors de la recherche financière: %s", exc)

                conversation.model = model
                conversation.updated_at = now()
                auto_title_eligible = False
                if not conversation.messages or len(conversation.messages) <= 1:
                    if conversation.title == "Nouvelle conversation":
                        auto_title_eligible = True
                        conversation.title = (body.content.strip() or attachments[0].filename)[:70]
                needs_classification = auto_title_eligible or not conversation.theme or not conversation.keywords
                initial_title = conversation.title
                prompt_for_meta = body.content.strip() or (attachments[0].filename if attachments else "")
                db.commit()
                db.refresh(message)
                user_message = message_json(message)
                assistant_id = str(uuid4())
        except providers.ProviderError as exc:
            lock.release()
            raise HTTPException(502, str(exc)) from exc
        except Exception:
            lock.release()
            raise

        async def _search_with_limit(query_text: str, limit: int) -> list[dict[str, str]]:
            try:
                return await providers.search_web(settings, query_text, limit=limit)
            except TypeError:
                return await providers.search_web(settings, query_text)

        async def stream():
            accumulated = ""
            sources = []
            try:
                yield sse("meta", {"user_message": user_message, "assistant_message_id": assistant_id})
                with sessions() as db:
                    u_skills = list(db.scalars(select(Skill).where(Skill.user_id == user.id)))
                    init_active_skills = [s.name for s in (extract_mentioned_skills(body.content, u_skills) + [s for s in u_skills if s.id in body.skill_ids])]
                if init_active_skills:
                    yield sse("status", {"message": f"Compétence active · {' · '.join(init_active_skills)}…"})
                finance_items = [
                    item for item in attachments
                    if item.filename.startswith("📈") or (isinstance(item.extraction, dict) and item.extraction.get("model") in ("yahoo-finance", "eod-historical-data"))
                ]
                for f_item in finance_items:
                    ext = f_item.extraction if isinstance(f_item.extraction, dict) else {}
                    symbol = ext.get("symbol") or "Actif"
                    short_name = ext.get("short_name") or f_item.filename
                    price = ext.get("price")
                    curr = ext.get("currency") or "USD"
                    chg = ext.get("change_percent")
                    chg_str = f" ({chg:+.2f}%)" if chg is not None else ""
                    price_str = f"{price} {curr}{chg_str}" if price is not None else ""
                    is_eod = ext.get("model") == "eod-historical-data" or ext.get("provider") == "eodhd"
                    provider_name = "EOD Historical Data" if is_eod else "Yahoo Finance"
                    sources.append({
                        "title": f"{provider_name} · {short_name} ({symbol})",
                        "url": ext.get("url") or (f"https://eodhd.com/financial-summary/{symbol}" if is_eod else f"https://finance.yahoo.com/quote/{symbol}"),
                        "snippet": f"Cours : {price_str} · Données financières téléchargées en direct via l'API {ext.get('source_label') or provider_name}.",
                        "provider": "eodhd" if is_eod else "yahoo_finance",
                    })
                if finance_failures:
                    yield sse("status", {"message": f"⚠️ Données financières introuvables pour : {', '.join(finance_failures)}"})
                elif finance_items:
                    providers_used = sorted({s["title"].split(" · ")[0] for s in sources if s.get("provider") in ("eodhd", "yahoo_finance")})
                    yield sse("status", {"message": f"📈 Données live téléchargées · {' + '.join(providers_used)}"})

                has_web_attachment = any(
                    item.mime_type.startswith("text/html") or (isinstance(item.extraction, dict) and item.extraction.get("url"))
                    for item in attachments
                )
                if has_web_attachment and not body.deep_search and not body.web_search:
                    has_youtube = any(
                        item.filename.startswith("🎬") or (isinstance(item.extraction, dict) and item.extraction.get("model") == "youtube-transcript")
                        for item in attachments
                    )
                    has_finance = bool(finance_items)
                    if has_youtube:
                        status_text = "Analyse de la vidéo YouTube et de sa transcription…"
                    elif has_finance:
                        symbols_label = ", ".join(
                            f_item.extraction.get("symbol", "Actif")
                            for f_item in finance_items
                            if isinstance(f_item.extraction, dict) and f_item.extraction.get("symbol")
                        ) or "marché"
                        status_text = f"Données financières en direct ({symbols_label}) · Synthèse des cours en cours…"
                    else:
                        status_text = "Analyse et synthèse des pages web jointes…"
                    yield sse("status", {"message": status_text})
                if body.deep_search:
                    raw_query = body.content.strip()[:1500]
                    with sessions() as db:
                        conversation = get_conversation(db, conversation_id, user.id)
                        search_summary = conversation.summary
                        search_context = [{"role": item.role, "content": item.content}
                                          for item in conversation.messages[:-1][-4:]]
                    yield sse("status", {"message": "DeepSearch · Planification des pistes multilingues…"})
                    try:
                        queries = await providers.plan_deep_search_queries(
                            settings, raw_query, search_summary, search_context,
                        )
                    except providers.ProviderError as exc:
                        _logger.warning("Planification DeepSearch indisponible; repli sur question directe: %s", exc)
                        queries = [raw_query]
                    last_search_error: providers.ProviderError | None = None
                    successful_searches = 0
                    for idx, sub_query in enumerate(queries, start=1):
                        if len(sources) >= 40:
                            break
                        yield sse("status", {"message": f"DeepSearch · Exploration ({idx}/{len(queries)}) : « {sub_query[:70]} »…"})
                        try:
                            batch = await _search_with_limit(sub_query, 10)
                            successful_searches += 1
                            sources = providers.merge_web_sources(sources, batch, query=sub_query, max_total=40)
                        except providers.ProviderError as exc:
                            last_search_error = exc
                    if successful_searches == 0 and last_search_error is not None:
                        raise last_search_error
                    if sources and len(sources) < 40:
                        yield sse("status", {"message": f"DeepSearch · Analyse de {len(sources)} sources et recherche internationale complémentaire…"})
                        try:
                            followup_queries = await providers.plan_deep_search_followup(
                                settings, raw_query, queries, sources,
                            )
                        except providers.ProviderError as exc:
                            _logger.warning("Approfondissement DeepSearch ignoré: %s", exc)
                            followup_queries = []
                        for idx, sub_query in enumerate(followup_queries, start=1):
                            if len(sources) >= 40:
                                break
                            yield sse("status", {"message": f"DeepSearch · Approfondissement ({idx}/{len(followup_queries)}) : « {sub_query[:70]} »…"})
                            try:
                                batch = await _search_with_limit(sub_query, 10)
                                sources = providers.merge_web_sources(sources, batch, query=sub_query, max_total=40)
                            except providers.ProviderError as exc:
                                _logger.warning("Requête complémentaire DeepSearch en échec (%r): %s", sub_query, exc)
                    if sources and not settings.demo_mode:
                        yield sse("status", {"message": f"DeepSearch · Traduction et préparation des {len(sources)} sources…"})
                        sources = await providers.translate_deep_search_sources(settings, sources, raw_query)
                elif body.web_search:
                    query = body.content.strip()[:1000]
                    with sessions() as db:
                        conversation = get_conversation(db, conversation_id, user.id)
                        search_summary = conversation.summary
                        search_context = [{"role": item.role, "content": item.content}
                                          for item in conversation.messages[:-1][-4:]]
                    if (
                        providers.stream_chat is _DEFAULT_STREAM_CHAT
                        or providers.rewrite_search_query is not _DEFAULT_REWRITE_SEARCH_QUERY
                    ):
                        yield sse("status", {"message": "Reformulation de la recherche…"})
                        try:
                            query = await providers.rewrite_search_query(
                                settings, query, search_summary, search_context,
                            )
                        except providers.ProviderError as exc:
                            _logger.warning("Reformulation de recherche indisponible; question originale conservée: %s", exc)
                            yield sse("status", {"message": "Reformulation indisponible; recherche avec la question originale…"})
                    yield sse("status", {"message": "Recherche web en cours…"})
                    sources = await providers.search_web(settings, query)
                    if not sources:
                        raise providers.ProviderError(
                            "Aucune source web exploitable n’a été trouvée. "
                            "Reformulez ou désactivez Web pour continuer sans recherche.")
                    if notice := sources[0].get("search_notice"):
                        yield sse("status", {"message": notice})
                # Summarize old turns, retaining the complete persisted history.
                with sessions() as db:
                    conversation = get_conversation(db, conversation_id, user.id)
                    history = conversation.messages
                    cutoff = max(0, len(history) - 6)
                    should_summarize = len(history) - conversation.summary_through >= settings.summary_every_messages and cutoff > conversation.summary_through
                    previous_summary = conversation.summary
                    transcript_parts = []
                    transcript_size = 0
                    summary_cutoff = conversation.summary_through
                    for item in history[conversation.summary_through:cutoff]:
                        item_text = f"{item.role}: {item.content[:4000]}"
                        for attachment in item.attachments:
                            attachment_text = extraction_text(attachment.extraction, 4000) if attachment.extraction else attachment.extracted_text[:4000]
                            item_text += f"\n[Pièce jointe : {attachment.filename}]\n{attachment_text}"
                        # Do not mark unsummarized turns as covered if the input
                        # budget forces this summary to consume only part of them.
                        item_text = item_text[:12000]
                        if transcript_parts and transcript_size + len(item_text) > 24000:
                            break
                        transcript_parts.append(item_text)
                        transcript_size += len(item_text)
                        summary_cutoff += 1
                    transcript = "\n".join(transcript_parts)
                if should_summarize:
                    yield sse("status", {"message": "Mise à jour du résumé de la conversation…"})
                    try:
                        if settings.demo_mode:
                            summary = "[Résumé de démonstration, extraits du dialogue]\n" + (previous_summary + "\n" + transcript)[-settings.max_summary_chars:]
                        else:
                            summary = await providers.summarize(settings, settings.summary_model, previous_summary, transcript)
                        with sessions() as db:
                            conversation = get_conversation(db, conversation_id, user.id)
                            conversation.summary = summary[:settings.max_summary_chars]
                            conversation.summary_through = summary_cutoff
                            db.commit()
                    except providers.ProviderError:
                        yield sse("status", {"message": "Résumé temporairement indisponible ; utilisation des messages récents dans la limite du contexte."})
                with sessions() as db:
                    conversation = get_conversation(db, conversation_id, user.id)
                    memories = [item.content for item in db.scalars(select(Memory).where(
                        Memory.user_id == user.id).order_by(Memory.created_at))]
                    u_skills = list(db.scalars(select(Skill).where(Skill.user_id == user.id)))
                    explicit_skills = [s for s in u_skills if s.id in body.skill_ids]
                    mentioned_skills = extract_mentioned_skills(body.content, u_skills)
                    conv_skills = [link.skill for link in conversation.skill_links]
                    merged_skills = []
                    seen_skill_ids = set()
                    for s in (mentioned_skills + explicit_skills + conv_skills):
                        if s.id not in seen_skill_ids:
                            seen_skill_ids.add(s.id)
                            merged_skills.append(s)
                    skills = [{"name": s.name, "prompt": s.prompt} for s in merged_skills]
                    history = [{"role": item.role, "content": item.content, "attachments": [
                        {"filename": attachment.filename, "mime_type": attachment.mime_type,
                         "extracted_text": attachment.extracted_text, "extraction": attachment.extraction,
                         "path": str(upload_dir / attachment.storage_name)}
                        for attachment in item.attachments]} for item in conversation.messages[conversation.summary_through:]]
                    summary = conversation.summary
                if settings.demo_mode:
                    if body.code_mode:
                        prompt_summary = (body.content.strip() or "Application de démonstration")[:80]
                        response = (
                            f"Voici un projet multi-fichiers généré en **Mode Code Canvas** pour : « {prompt_summary} ».\n\n"
                            "```html path=\"index.html\"\n"
                            "<!DOCTYPE html>\n<html lang=\"fr\">\n<head>\n  <meta charset=\"UTF-8\" />\n"
                            "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
                            "  <title>Application Canvas</title>\n  <link rel=\"stylesheet\" href=\"styles.css\" />\n"
                            "</head>\n<body>\n  <main class=\"app-card\">\n    <h1>Application Canvas</h1>\n"
                            f"    <p id=\"subtitle\">{prompt_summary}</p>\n"
                            "    <button id=\"action-btn\" type=\"button\">Tester l'interaction</button>\n"
                            "    <output id=\"output\"></output>\n  </main>\n  <script src=\"app.js\"></script>\n</body>\n</html>\n"
                            "```\n\n"
                            "```css path=\"styles.css\"\n"
                            "body { margin: 0; font-family: system-ui, sans-serif; background: #0f172a; color: #f8fafc; display: grid; place-items: center; min-height: 100vh; }\n"
                            ".app-card { background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 28px; max-width: 420px; text-align: center; box-shadow: 0 20px 40px rgba(0,0,0,0.35); }\n"
                            "button { margin-top: 12px; padding: 10px 18px; border-radius: 10px; border: 0; background: #6366f1; color: white; font-weight: 600; cursor: pointer; }\n"
                            "output { display: block; margin-top: 14px; color: #38bdf8; font-weight: 600; }\n"
                            "```\n\n"
                            "```javascript path=\"app.js\"\n"
                            "const btn = document.getElementById('action-btn');\n"
                            "const out = document.getElementById('output');\n"
                            "let count = 0;\n"
                            "btn?.addEventListener('click', () => {\n"
                            "  count += 1;\n"
                            "  if (out) out.textContent = `Interaction #${count} exécutée avec succès !`;\n"
                            "});\n"
                            "```\n\n"
                            "```markdown path=\"README.md\"\n"
                            f"# Projet Canvas\n\nDemande : {prompt_summary}\n\n## Fichiers\n- `index.html`\n- `styles.css`\n- `app.js`\n```\n"
                        )
                    else:
                        response = ("**Mode démonstration — aucune IA externe n'est appelée.**\n\n"
                                    f"Votre message a été enregistré : « {body.content.strip() or 'Document joint'} ».\n\n"
                                    "L'historique, les pièces jointes et les souvenirs fonctionnent localement. "
                                    "Configurez une clé LLM et désactivez DEMO_MODE pour obtenir de vraies réponses.")
                    for offset in range(0, len(response), 32):
                        chunk = response[offset:offset + 32]
                        accumulated += chunk
                        yield sse("delta", {"text": chunk})
                        await asyncio.sleep(0.005)
                else:
                    context = build_context(
                        settings, summary, memories, history, sources,
                        model_info["vision"], skills, deep_search=body.deep_search,
                        code_mode=body.code_mode,
                    )
                    if body.deep_search:
                        status_label = f"DeepSearch · Synthèse globale de {len(sources)} source{'s' if len(sources) != 1 else ''}…"
                    elif body.code_mode:
                        status_label = "Canvas Code · Conception et génération des fichiers…"
                    else:
                        status_label = "Rédaction de la réponse…"
                    yield sse("status", {"message": status_label})
                    async for chunk in providers.stream_chat(settings, context, model):
                        accumulated += chunk
                        if len(accumulated) > 160000:
                            raise providers.ProviderError("La réponse dépasse la limite autorisée")
                        yield sse("delta", {"text": chunk})
                    if not accumulated.strip():
                        # Some reasoning models occasionally spend the whole turn
                        # thinking and close the stream without visible content.
                        _logger.warning("Réponse vide du modèle %s ; nouvelle tentative", model)
                        yield sse("status", {"message": "Réponse vide du modèle · nouvelle tentative…"})
                        retry_context = context + [{"role": "system", "content": (
                            "Ta tentative précédente n'a produit aucun texte visible. Réponds maintenant directement "
                            "à l'utilisateur en t'appuyant sur les données disponibles ; si une donnée manque, dis-le "
                            "explicitement plutôt que de ne rien répondre.")}]
                        async for chunk in providers.stream_chat(settings, retry_context, model):
                            accumulated += chunk
                            if len(accumulated) > 160000:
                                raise providers.ProviderError("La réponse dépasse la limite autorisée")
                            yield sse("delta", {"text": chunk})
                if not accumulated.strip():
                    raise providers.ProviderError("Le fournisseur a retourné une réponse vide (deux tentatives). Réessayez ou changez de modèle.")
                generated_meta: dict | None = None
                if needs_classification:
                    use_real_classifier = (
                        not settings.demo_mode
                        and settings.enabled(settings.llm_api_key)
                        and (
                            providers.stream_chat is _DEFAULT_STREAM_CHAT
                            or providers.classify_conversation is not _DEFAULT_CLASSIFY_CONVERSATION
                        )
                    )
                    if use_real_classifier:
                        yield sse("status", {"message": "Organisation · Titre, thème et mots-clés…"})
                        try:
                            generated_meta = await providers.classify_conversation(
                                settings, prompt_for_meta, accumulated, current_title=initial_title,
                            )
                        except providers.ProviderError as exc:
                            _logger.warning("Classification automatique indisponible; repli local: %s", exc)
                            generated_meta = providers.fallback_conversation_metadata(
                                prompt_for_meta, accumulated, current_title=initial_title,
                            )
                            generated_meta["keep_initial_title"] = True
                    else:
                        generated_meta = providers.fallback_conversation_metadata(
                            prompt_for_meta, accumulated, current_title=initial_title,
                        )
                        generated_meta["keep_initial_title"] = True
                with sessions() as db:
                    conversation = get_conversation(db, conversation_id, user.id)
                    answer = Message(id=assistant_id, conversation_id=conversation_id, role="assistant", content=accumulated, sources=sources)
                    db.add(answer)
                    if generated_meta:
                        if auto_title_eligible and not generated_meta.get("keep_initial_title") and generated_meta.get("title"):
                            conversation.title = generated_meta["title"][:200]
                        if not conversation.theme and generated_meta.get("theme"):
                            conversation.theme = generated_meta["theme"][:80]
                        if not conversation.keywords and generated_meta.get("keywords"):
                            conversation.keywords = generated_meta["keywords"][:5]
                    conversation.updated_at = now()
                    db.commit()
                    db.refresh(conversation)
                    yield sse("done", {"message": message_json(answer), "conversation": conversation_json(conversation)})
            except asyncio.CancelledError:
                # A closed browser must not leave the conversation locked.
                raise
            except providers.ProviderError as exc:
                yield sse("error", {"message": str(exc)})
            except Exception:
                yield sse("error", {"message": "Impossible de terminer la réponse. Votre message reste enregistré ; réessayez."})
            finally:
                lock.release()

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/images")
    def list_generated_images(user: User = Depends(current_user)):
        with sessions() as db:
            return [generated_image_json(item) for item in db.scalars(
                select(GeneratedImage).where(GeneratedImage.user_id == user.id)
                .order_by(GeneratedImage.created_at.desc(), GeneratedImage.id.desc()))]

    @app.post("/api/images/improve")
    async def improve_image(body: ImproveImagePrompt, user: User = Depends(current_user)):
        if settings.demo_mode or not settings.enabled(settings.llm_api_key):
            raise HTTPException(503, "L'amélioration du prompt nécessite une clé LLM_API_KEY et le mode IA réel")
        model = (body.model.strip() if body.model and body.model.strip() else None) or settings.image_prompt_model or settings.default_model
        try:
            prompt = await providers.improve_image_prompt(settings, model, body.prompt, body.style_keywords, body.negative_prompt)
        except providers.ProviderError as exc:
            raise HTTPException(502, str(exc)) from exc
        return {"prompt": prompt}

    @app.post("/api/images", status_code=201)
    async def create_studio_image(body: CreateImage, user: User = Depends(current_user)):
        is_ideogram = body.model == "ideogram"
        if is_ideogram and not settings.enabled(settings.ideogram_api_key):
            raise HTTPException(503, "La génération d'image avec Ideogram nécessite IDEOGRAM_API_KEY et un mode IA réel")
        if not is_ideogram and not settings.enabled(settings.llm_api_key):
            raise HTTPException(503, "La génération d'image avec ce modèle nécessite LLM_API_KEY et un mode IA réel")
        if body.aspect_ratio not in IMAGE_ASPECT_RATIOS:
            raise HTTPException(422, "Ratio d'image non pris en charge")
        with sessions() as db:
            count = db.scalar(select(func.count()).select_from(GeneratedImage).where(GeneratedImage.user_id == user.id))
            if count >= MAX_GENERATED_IMAGES:
                raise HTTPException(422, f"Limite de {MAX_GENERATED_IMAGES} images sauvegardées atteinte ; supprimez d'anciennes images")
        lock = claim(user.id, "image-studio")
        await lock.acquire()
        path = None
        try:
            content, mime = await providers.generate_image(
                settings, body.prompt, body.aspect_ratio, body.negative_prompt, model=body.model
            )
            storage_name = str(uuid4())
            path = upload_dir / storage_name
            path.write_bytes(content)
            extension = {"image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(mime, "jpg")
            model_prefix = "ideogram" if is_ideogram else re.sub(r"[^a-zA-Z0-9_-]", "-", body.model.split("/")[-1])[:24]
            with sessions() as db:
                image_id = str(uuid4())
                item = GeneratedImage(
                    id=image_id, user_id=user.id, prompt=body.prompt, aspect_ratio=body.aspect_ratio,
                    filename=f"{model_prefix}-{image_id[:8]}.{extension}", mime_type=mime,
                    size=len(content), storage_name=storage_name,
                )
                db.add(item)
                db.commit()
                db.refresh(item)
                return generated_image_json(item)
        except providers.ProviderError as exc:
            if path:
                path.unlink(missing_ok=True)
            raise HTTPException(502, str(exc)) from exc
        except Exception:
            if path:
                path.unlink(missing_ok=True)
            raise
        finally:
            lock.release()

    @app.get("/api/images/{image_id}/file")
    def generated_image_file(image_id: str, download: bool = False, user: User = Depends(current_user)):
        with sessions() as db:
            item = db.scalar(select(GeneratedImage).where(GeneratedImage.id == image_id, GeneratedImage.user_id == user.id))
            if not item or not (upload_dir / item.storage_name).is_file():
                raise HTTPException(404, "Image introuvable")
            return FileResponse(upload_dir / item.storage_name, media_type=item.mime_type, filename=item.filename,
                                content_disposition_type="attachment" if download else "inline",
                                headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})

    @app.delete("/api/images/{image_id}", status_code=204)
    def delete_generated_image(image_id: str, user: User = Depends(current_user)):
        with sessions() as db:
            item = db.scalar(select(GeneratedImage).where(
                GeneratedImage.id == image_id, GeneratedImage.user_id == user.id).with_for_update())
            if not item:
                raise HTTPException(404, "Image introuvable")
            storage_name = item.storage_name
            db.delete(item)
            db.commit()
        (upload_dir / storage_name).unlink(missing_ok=True)
        return Response(status_code=204)

    @app.post("/api/conversations/{conversation_id}/images", status_code=201)
    async def create_image(conversation_id: str, body: CreateImage, user: User = Depends(current_user)):
        is_ideogram = body.model == "ideogram"
        if is_ideogram and not settings.enabled(settings.ideogram_api_key):
            raise HTTPException(503, "La génération d'image avec Ideogram nécessite IDEOGRAM_API_KEY et un mode IA réel")
        if not is_ideogram and not settings.enabled(settings.llm_api_key):
            raise HTTPException(503, "La génération d'image avec ce modèle nécessite LLM_API_KEY et un mode IA réel")
        if body.aspect_ratio not in IMAGE_ASPECT_RATIOS:
            raise HTTPException(422, "Ratio d'image non pris en charge")
        lock = claim(user.id, conversation_id)
        await lock.acquire()
        path = None
        try:
            with sessions() as db:
                get_conversation(db, conversation_id, user.id)
            content, mime = await providers.generate_image(
                settings, body.prompt, body.aspect_ratio, body.negative_prompt, model=body.model
            )
            storage_name = str(uuid4())
            path = upload_dir / storage_name
            path.write_bytes(content)
            model_label = "Ideogram" if is_ideogram else body.model
            model_prefix = "ideogram" if is_ideogram else re.sub(r"[^a-zA-Z0-9_-]", "-", body.model.split("/")[-1])[:24]
            with sessions() as db:
                conversation = get_conversation(db, conversation_id, user.id)
                prompt = Message(conversation_id=conversation_id, role="user", content=f"Génère une image : {body.prompt}")
                answer = Message(conversation_id=conversation_id, role="assistant", content=f"Image générée avec {model_label} : {body.prompt}")
                db.add_all([prompt, answer])
                db.flush()
                extension = {"image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(mime, "jpg")
                attachment = Attachment(user_id=user.id, filename=f"{model_prefix}.{extension}", mime_type=mime,
                                        size=len(content), storage_name=storage_name, message_id=answer.id)
                db.add(attachment)
                conversation.updated_at = now()
                db.commit()
                db.refresh(answer)
                return message_json(answer)
        except providers.ProviderError as exc:
            if path:
                path.unlink(missing_ok=True)
            raise HTTPException(502, str(exc)) from exc
        except Exception:
            if path:
                path.unlink(missing_ok=True)
            raise
        finally:
            lock.release()

    @app.get("/api/blogs")
    def list_blogs(user: User = Depends(current_user)):
        with sessions() as db:
            items = list(db.scalars(
                select(Blog)
                .where(Blog.user_id == user.id)
                .order_by(Blog.updated_at.desc())
            ))
            return [blog_json(item) for item in items]

    @app.post("/api/blogs", status_code=201)
    async def create_blog(body: CreateBlog, user: User = Depends(current_user)):
        with sessions() as db:
            count = db.scalar(select(func.count(Blog.id)).where(Blog.user_id == user.id))
            if count and count >= 50:
                raise HTTPException(422, "Nombre maximal de blogs atteint (50)")

        blog_title = body.title or (body.prompt[:60].strip().capitalize())
        try:
            post_title, post_summary, post_content, sources = await generate_blog_edition(
                settings, body.prompt, blog_title=blog_title
            )
        except providers.ProviderError as exc:
            raise HTTPException(502, f"Erreur lors de la génération du blog : {exc}") from exc

        final_title = body.title or post_title[:200]
        with sessions() as db:
            blog = Blog(
                user_id=user.id,
                title=final_title,
                prompt=body.prompt,
                auto_refresh=body.auto_refresh,
                theme=body.theme or "sunset",
            )
            db.add(blog)
            db.flush()

            post = BlogPost(
                blog_id=blog.id,
                title=post_title,
                summary=post_summary,
                content=post_content,
                sources=sources,
            )
            db.add(post)
            blog.updated_at = now()
            db.commit()
            db.refresh(blog)
            return blog_json(blog, include_posts=True)

    @app.get("/api/blogs/{blog_id}")
    def get_blog_endpoint(blog_id: str, user: User = Depends(current_user)):
        with sessions() as db:
            blog = db.scalar(select(Blog).where(Blog.id == blog_id, Blog.user_id == user.id))
            if not blog:
                raise HTTPException(404, "Blog introuvable")
            return blog_json(blog, include_posts=True)

    @app.patch("/api/blogs/{blog_id}")
    def update_blog(blog_id: str, body: UpdateBlog, user: User = Depends(current_user)):
        with sessions() as db:
            blog = db.scalar(select(Blog).where(Blog.id == blog_id, Blog.user_id == user.id))
            if not blog:
                raise HTTPException(404, "Blog introuvable")
            if body.title is not None:
                blog.title = body.title
            if body.prompt is not None:
                blog.prompt = body.prompt
            if body.auto_refresh is not None:
                blog.auto_refresh = body.auto_refresh
            if body.theme is not None:
                blog.theme = body.theme
            blog.updated_at = now()
            db.commit()
            db.refresh(blog)
            return blog_json(blog, include_posts=True)

    @app.delete("/api/blogs/{blog_id}", status_code=204)
    def delete_blog(blog_id: str, user: User = Depends(current_user)):
        with sessions() as db:
            blog = db.scalar(select(Blog).where(Blog.id == blog_id, Blog.user_id == user.id))
            if not blog:
                raise HTTPException(404, "Blog introuvable")
            db.delete(blog)
            db.commit()
        return Response(status_code=204)

    @app.post("/api/blogs/{blog_id}/refresh")
    async def refresh_blog(blog_id: str, user: User = Depends(current_user)):
        with sessions() as db:
            blog = db.scalar(select(Blog).where(Blog.id == blog_id, Blog.user_id == user.id))
            if not blog:
                raise HTTPException(404, "Blog introuvable")
            prompt = blog.prompt
            title = blog.title

        try:
            post_title, post_summary, post_content, sources = await generate_blog_edition(
                settings, prompt, blog_title=title
            )
        except providers.ProviderError as exc:
            raise HTTPException(502, f"Erreur lors de l'actualisation du blog : {exc}") from exc

        with sessions() as db:
            blog = db.scalar(select(Blog).where(Blog.id == blog_id, Blog.user_id == user.id))
            if not blog:
                raise HTTPException(404, "Blog introuvable")
            post = BlogPost(
                blog_id=blog.id,
                title=post_title,
                summary=post_summary,
                content=post_content,
                sources=sources,
            )
            db.add(post)
            blog.updated_at = now()
            db.commit()
            db.refresh(blog)
            return {
                "blog": blog_json(blog, include_posts=True),
                "new_post": blog_post_json(post),
            }

    @app.delete("/api/blogs/{blog_id}/posts/{post_id}", status_code=204)
    def delete_blog_post(blog_id: str, post_id: str, user: User = Depends(current_user)):
        with sessions() as db:
            blog = db.scalar(select(Blog).where(Blog.id == blog_id, Blog.user_id == user.id))
            if not blog:
                raise HTTPException(404, "Blog introuvable")
            post = db.scalar(select(BlogPost).where(BlogPost.id == post_id, BlogPost.blog_id == blog.id))
            if not post:
                raise HTTPException(404, "Édition introuvable")
            db.delete(post)
            db.commit()
        return Response(status_code=204)

    return app



app = create_app()
