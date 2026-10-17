import asyncio
import json
from contextlib import asynccontextmanager
from datetime import timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session, sessionmaker

from . import providers
from .config import Settings
from .context import build_context
from .documents import extract_document
from .models import Attachment, Base, Conversation, Memory, Message, now
from .schemas import CreateConversation, CreateImage, CreateMemory, SendMessage, UpdateConversation


def stamp(value) -> str:
    return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()


def attachment_json(item: Attachment) -> dict:
    return {"id": item.id, "filename": item.filename, "mime_type": item.mime_type, "size": item.size,
            "url": f"/api/attachments/{item.id}/file", "created_at": stamp(item.created_at),
            "extracted_chars": len(item.extracted_text)}


def message_json(item: Message) -> dict:
    return {"id": item.id, "role": item.role, "content": item.content, "created_at": stamp(item.created_at),
            "attachments": [attachment_json(value) for value in item.attachments], "sources": item.sources}


def conversation_json(item: Conversation, detail: bool = False) -> dict:
    result = {"id": item.id, "title": item.title, "model": item.model, "created_at": stamp(item.created_at),
              "updated_at": stamp(item.updated_at), "summary": item.summary}
    if detail:
        result["messages"] = [message_json(message) for message in item.messages]
    return result


def sse(name: str, value: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(value, ensure_ascii=False)}\n\n"


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

    @asynccontextmanager
    async def lifespan(_app):
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(title="cLAIr", version="0.1.0", lifespan=lifespan)
    app.state.settings, app.state.sessions = settings, sessions
    app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type"])

    def get_conversation(db: Session, conversation_id: str) -> Conversation:
        item = db.get(Conversation, conversation_id)
        if not item:
            raise HTTPException(404, "Conversation introuvable")
        return item

    def check_model(model: str) -> dict:
        found = next((item for item in models if item["id"] == model), None)
        if not found:
            raise HTTPException(422, "Modèle absent de LLM_MODELS")
        return found

    def claim(conversation_id: str) -> asyncio.Lock:
        lock = locks.setdefault(conversation_id, asyncio.Lock())
        if lock.locked():
            raise HTTPException(409, "Une réponse est déjà en cours dans cette conversation")
        return lock

    @app.get("/api/health")
    def health():
        with sessions() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/api/config")
    def config():
        return {"models": models, "default_model": settings.default_model, "demo_mode": settings.demo_mode,
                "features": {"chat": settings.demo_mode or settings.enabled(settings.llm_api_key),
                             "web_search": settings.enabled(settings.brave_api_key),
                             "ocr": settings.enabled(settings.mistral_api_key),
                             "image_generation": settings.enabled(settings.ideogram_api_key)}}

    @app.get("/api/conversations")
    def list_conversations():
        with sessions() as db:
            return [conversation_json(item) for item in db.scalars(select(Conversation).order_by(Conversation.updated_at.desc()))]

    @app.post("/api/conversations", status_code=201)
    def new_conversation(body: CreateConversation):
        model = body.model or settings.default_model
        check_model(model)
        with sessions() as db:
            item = Conversation(title=body.title.strip() or "Nouvelle conversation", model=model)
            db.add(item)
            db.commit()
            return conversation_json(item, True)

    @app.get("/api/conversations/{conversation_id}")
    def read_conversation(conversation_id: str):
        with sessions() as db:
            return conversation_json(get_conversation(db, conversation_id), True)

    @app.patch("/api/conversations/{conversation_id}")
    def edit_conversation(conversation_id: str, body: UpdateConversation):
        if locks.get(conversation_id) and locks[conversation_id].locked():
            raise HTTPException(409, "Attendez la fin de la réponse")
        with sessions() as db:
            item = get_conversation(db, conversation_id)
            if body.title is not None:
                item.title = body.title.strip() or "Nouvelle conversation"
            if body.model is not None:
                check_model(body.model)
                item.model = body.model
            item.updated_at = now()
            db.commit()
            return conversation_json(item, True)

    @app.delete("/api/conversations/{conversation_id}", status_code=204)
    def delete_conversation(conversation_id: str):
        if locks.get(conversation_id) and locks[conversation_id].locked():
            raise HTTPException(409, "Attendez la fin de la réponse")
        with sessions() as db:
            item = get_conversation(db, conversation_id)
            files = [attachment for message in item.messages for attachment in message.attachments]
            names = [attachment.storage_name for attachment in files]
            for attachment in files:
                db.delete(attachment)
            db.delete(item)
            db.commit()
        for name in names:
            (upload_dir / name).unlink(missing_ok=True)
        locks.pop(conversation_id, None)
        return Response(status_code=204)

    @app.get("/api/memories")
    def list_memories():
        with sessions() as db:
            return [{"id": item.id, "content": item.content, "created_at": stamp(item.created_at)}
                    for item in db.scalars(select(Memory).order_by(Memory.created_at))]

    @app.post("/api/memories", status_code=201)
    def add_memory(body: CreateMemory):
        if not body.content.strip():
            raise HTTPException(422, "Le souvenir ne peut pas être vide")
        with sessions() as db:
            if len(db.scalars(select(Memory)).all()) >= 100:
                raise HTTPException(422, "Limite de 100 souvenirs atteinte")
            item = Memory(content=body.content.strip())
            db.add(item)
            db.commit()
            return {"id": item.id, "content": item.content, "created_at": stamp(item.created_at)}

    @app.delete("/api/memories/{memory_id}", status_code=204)
    def delete_memory(memory_id: str):
        with sessions() as db:
            item = db.get(Memory, memory_id)
            if not item:
                raise HTTPException(404, "Souvenir introuvable")
            db.delete(item)
            db.commit()
        return Response(status_code=204)

    @app.post("/api/attachments", status_code=201)
    async def upload(file: UploadFile = File(...)):
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
            mime, extracted = await extract_document(settings, content, filename)
        except providers.ProviderError as exc:
            raise HTTPException(502, str(exc)) from exc
        if mime.startswith("image/") and len(content) > 8 * 1024 * 1024:
            raise HTTPException(413, "Les images sont limitées à 8 Mo pour la vision")
        storage_name = str(uuid4())
        path = upload_dir / storage_name
        path.write_bytes(content)
        try:
            with sessions() as db:
                item = Attachment(filename=filename, mime_type=mime, size=len(content), storage_name=storage_name, extracted_text=extracted)
                db.add(item)
                db.commit()
                return attachment_json(item)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    @app.get("/api/attachments/{attachment_id}/file")
    def attachment_file(attachment_id: str):
        with sessions() as db:
            item = db.get(Attachment, attachment_id)
            if not item or not (upload_dir / item.storage_name).is_file():
                raise HTTPException(404, "Pièce jointe introuvable")
            return FileResponse(upload_dir / item.storage_name, media_type=item.mime_type, filename=item.filename,
                                content_disposition_type="inline" if item.mime_type.startswith("image/") else "attachment",
                                headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"})

    @app.delete("/api/attachments/{attachment_id}", status_code=204)
    def delete_unattached_file(attachment_id: str):
        with sessions() as db:
            item = db.get(Attachment, attachment_id, with_for_update=True)
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
    async def send_message(conversation_id: str, body: SendMessage):
        if not settings.demo_mode and not settings.enabled(settings.llm_api_key):
            raise HTTPException(503, "Configurez LLM_API_KEY ou activez explicitement DEMO_MODE pour une simulation")
        if not body.content.strip() and not body.attachment_ids:
            raise HTTPException(422, "Écrivez un message ou joignez un document")
        if body.web_search and not settings.enabled(settings.brave_api_key):
            raise HTTPException(503, "La recherche web nécessite BRAVE_API_KEY et un mode IA réel")
        lock = claim(conversation_id)
        await lock.acquire()
        try:
            with sessions() as db:
                conversation = get_conversation(db, conversation_id)
                model = body.model or conversation.model
                model_info = check_model(model)
                attachments = []
                for attachment_id in body.attachment_ids:
                    item = db.get(Attachment, attachment_id, with_for_update=True)
                    if not item or item.message_id:
                        raise HTTPException(422, "Pièce jointe introuvable ou déjà utilisée")
                    attachments.append(item)
                if sum(item.mime_type.startswith("image/") for item in attachments) > 4:
                    raise HTTPException(422, "Joignez au maximum 4 images par message pour qu'elles soient toutes analysées")
                for item in attachments:
                    if item.mime_type.startswith("image/") and not model_info["vision"] and not settings.demo_mode:
                        if not settings.enabled(settings.mistral_api_key):
                            raise HTTPException(422, "Choisissez un modèle vision ou configurez MISTRAL_API_KEY pour lire cette image")
                        item.extracted_text = (await providers.extract_ocr(settings, (upload_dir / item.storage_name).read_bytes(), item.mime_type))[:40000]
                message = Message(conversation_id=conversation_id, role="user", content=body.content.strip())
                db.add(message)
                db.flush()
                for item in attachments:
                    item.message_id = message.id
                conversation.model = model
                conversation.updated_at = now()
                if not conversation.messages or len(conversation.messages) <= 1:
                    if conversation.title == "Nouvelle conversation":
                        conversation.title = (body.content.strip() or attachments[0].filename)[:70]
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

        async def stream():
            accumulated = ""
            sources = []
            try:
                yield sse("meta", {"user_message": user_message, "assistant_message_id": assistant_id})
                if body.web_search:
                    yield sse("status", {"message": "Recherche web en cours…"})
                    sources = await providers.search_web(settings, body.content[:1000])
                # Summarize old turns, retaining the complete persisted history.
                with sessions() as db:
                    conversation = get_conversation(db, conversation_id)
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
                            item_text += f"\n[Pièce jointe : {attachment.filename}]\n{attachment.extracted_text[:4000]}"
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
                            summary = await providers.summarize(settings, model, previous_summary, transcript)
                        with sessions() as db:
                            conversation = get_conversation(db, conversation_id)
                            conversation.summary = summary[:settings.max_summary_chars]
                            conversation.summary_through = summary_cutoff
                            db.commit()
                    except providers.ProviderError:
                        yield sse("status", {"message": "Résumé temporairement indisponible ; utilisation des messages récents dans la limite du contexte."})
                with sessions() as db:
                    conversation = get_conversation(db, conversation_id)
                    memories = [item.content for item in db.scalars(select(Memory).order_by(Memory.created_at))]
                    history = [{"role": item.role, "content": item.content, "attachments": [
                        {"filename": attachment.filename, "mime_type": attachment.mime_type,
                         "extracted_text": attachment.extracted_text, "path": str(upload_dir / attachment.storage_name)}
                        for attachment in item.attachments]} for item in conversation.messages[conversation.summary_through:]]
                    summary = conversation.summary
                if settings.demo_mode:
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
                    context = build_context(settings, summary, memories, history, sources, model_info["vision"])
                    yield sse("status", {"message": "Rédaction de la réponse…"})
                    async for chunk in providers.stream_chat(settings, context, model):
                        accumulated += chunk
                        if len(accumulated) > 100000:
                            raise providers.ProviderError("La réponse dépasse la limite autorisée")
                        yield sse("delta", {"text": chunk})
                if not accumulated.strip():
                    raise providers.ProviderError("Le fournisseur a retourné une réponse vide")
                with sessions() as db:
                    conversation = get_conversation(db, conversation_id)
                    answer = Message(id=assistant_id, conversation_id=conversation_id, role="assistant", content=accumulated, sources=sources)
                    db.add(answer)
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

    @app.post("/api/conversations/{conversation_id}/images", status_code=201)
    async def create_image(conversation_id: str, body: CreateImage):
        if not settings.enabled(settings.ideogram_api_key):
            raise HTTPException(503, "La génération d'image nécessite IDEOGRAM_API_KEY et un mode IA réel")
        if body.aspect_ratio not in {"1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"}:
            raise HTTPException(422, "Ratio d'image non pris en charge")
        lock = claim(conversation_id)
        await lock.acquire()
        path = None
        try:
            with sessions() as db:
                get_conversation(db, conversation_id)
            content, mime = await providers.generate_image(settings, body.prompt, body.aspect_ratio)
            storage_name = str(uuid4())
            path = upload_dir / storage_name
            path.write_bytes(content)
            with sessions() as db:
                conversation = get_conversation(db, conversation_id)
                prompt = Message(conversation_id=conversation_id, role="user", content=f"Génère une image : {body.prompt}")
                answer = Message(conversation_id=conversation_id, role="assistant", content=f"Image générée avec Ideogram : {body.prompt}")
                db.add_all([prompt, answer])
                db.flush()
                extension = {"image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(mime, "jpg")
                attachment = Attachment(filename=f"ideogram.{extension}", mime_type=mime, size=len(content), storage_name=storage_name, message_id=answer.id)
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

    return app


app = create_app()
