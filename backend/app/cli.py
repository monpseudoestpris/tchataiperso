import argparse
from getpass import getpass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from .auth import hash_password
from .config import Settings
from .models import Attachment, Conversation, Memory, User
from .schemas import LoginRequest


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_REVISION = "0001_auth_owner_nullable"


def upgrade(settings: Settings, revision: str) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", settings.db_url.replace("%", "%%"))
    command.upgrade(config, revision)


def prepare_schema(settings: Settings) -> None:
    engine = create_engine(settings.db_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()
    if current is None:
        upgrade(settings, SCHEMA_REVISION)
    elif current not in {
        SCHEMA_REVISION,
        "0002_require_data_owner",
        "0003_add_skills",
        "0004_attachment_extraction",
        "0005_add_generated_images",
        "0006_add_conversation_metadata",
        "0007_add_blogs_and_posts",
        "0008_add_blog_theme",
        "0009_add_deep_search_reports",
    }:
        raise SystemExit(f"Révision de base non reconnue : {current}")


def create_admin(settings: Settings, username: str) -> None:
    username = LoginRequest(username=username, password="temporary-validation-password").username
    prepare_schema(settings)
    engine = create_engine(settings.db_url, pool_pre_ping=True)
    sessions = sessionmaker(engine, expire_on_commit=False)
    try:
        with sessions.begin() as db:
            if db.scalar(select(User.id).where(User.is_admin.is_(True))):
                print("Un administrateur existe déjà; aucun compte n'a été modifié.")
                return
        password = getpass("Mot de passe initial (12 caractères minimum) : ")
        confirmation = getpass("Confirmer le mot de passe : ")
        LoginRequest(username=username, password=password)
        if password != confirmation:
            raise SystemExit("Les mots de passe ne correspondent pas.")
        with sessions.begin() as db:
            db.add(User(username=username, password_hash=hash_password(password), is_admin=True))
    except IntegrityError as exc:
        raise SystemExit("Cet identifiant existe déjà.") from exc
    finally:
        engine.dispose()
    print(f"Administrateur {username} créé. Attribuez les données historiques avec migrate-legacy.")


def migrate_legacy(settings: Settings, username: str) -> None:
    username = LoginRequest(username=username, password="temporary-validation-password").username if username else ""
    prepare_schema(settings)
    engine = create_engine(settings.db_url, pool_pre_ping=True)
    sessions = sessionmaker(engine, expire_on_commit=False)
    try:
        with sessions.begin() as db:
            unowned_rows = sum(db.scalar(select(func.count()).select_from(model).where(model.user_id.is_(None)))
                               for model in (Conversation, Memory, Attachment))
            if not username and unowned_rows:
                raise SystemExit("Des données historiques existent; choisissez explicitement un admin avec --owner.")
            owner_query = select(User).where(User.is_admin.is_(True), User.active.is_(True))
            if username:
                owner_query = owner_query.where(User.username == username)
            owner = db.scalar(owner_query.order_by(User.created_at))
            if not owner:
                raise SystemExit("Le propriétaire doit être un administrateur actif existant.")
            for model in (Conversation, Memory, Attachment):
                db.execute(update(model).where(model.user_id.is_(None)).values(user_id=owner.id))
        upgrade(settings, "head")
    finally:
        engine.dispose()
    print(f"Données historiques attribuées à {username}; schéma finalisé.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Administration de l'authentification cLAIr")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("migrate-schema", help="ajouter les tables d'authentification et les colonnes de propriétaire")
    create_parser = commands.add_parser("create-admin", help="créer le premier administrateur")
    create_parser.add_argument("--username", required=True)
    migrate_parser = commands.add_parser("migrate-legacy", help="attribuer explicitement les données existantes")
    migrate_parser.add_argument("--owner", default="", help="nom d'utilisateur admin propriétaire de l'historique")
    args = parser.parse_args()
    settings = Settings(_env_file=ROOT.parent / ".env")

    if args.action == "migrate-schema":
        prepare_schema(settings)
        print("Schéma préparé. Créez le premier administrateur, puis attribuez les données historiques.")
    elif args.action == "create-admin":
        create_admin(settings, args.username)
    else:
        migrate_legacy(settings, args.owner)


if __name__ == "__main__":
    main()
