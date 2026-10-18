from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, text

from app import cli
from app.config import Settings


def create_legacy_database(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql("""
            CREATE TABLE conversations (
                id VARCHAR(36) PRIMARY KEY, title VARCHAR(200) NOT NULL, model VARCHAR(200) NOT NULL,
                created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, summary TEXT NOT NULL,
                summary_through INTEGER NOT NULL
            )
        """)
        connection.exec_driver_sql("""
            CREATE TABLE messages (
                id VARCHAR(36) PRIMARY KEY, conversation_id VARCHAR(36) NOT NULL,
                role VARCHAR(20) NOT NULL, content TEXT NOT NULL, created_at DATETIME NOT NULL,
                sources JSON NOT NULL, FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        connection.exec_driver_sql("""
            CREATE TABLE attachments (
                id VARCHAR(36) PRIMARY KEY, filename VARCHAR(255) NOT NULL, mime_type VARCHAR(120) NOT NULL,
                size INTEGER NOT NULL, storage_name VARCHAR(100) NOT NULL UNIQUE, extracted_text TEXT NOT NULL,
                created_at DATETIME NOT NULL, message_id VARCHAR(36),
                FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE SET NULL
            )
        """)
        connection.exec_driver_sql("""
            CREATE TABLE memories (
                id VARCHAR(36) PRIMARY KEY, content TEXT NOT NULL, created_at DATETIME NOT NULL
            )
        """)
        created = datetime.now(timezone.utc).isoformat()
        connection.execute(text("INSERT INTO conversations VALUES ('legacy-conversation', 'Old chat', 'model', :created, :created, '', 0)"), {"created": created})
        connection.execute(text("INSERT INTO messages VALUES ('legacy-message', 'legacy-conversation', 'user', 'Old message', :created, '[]')"), {"created": created})
        connection.execute(text("INSERT INTO attachments VALUES ('legacy-attachment', 'old.txt', 'text/plain', 3, 'legacy-file', 'old', :created, 'legacy-message')"), {"created": created})
        connection.execute(text("INSERT INTO memories VALUES ('legacy-memory', 'Old memory', :created)"), {"created": created})


def test_legacy_rows_are_assigned_to_explicit_admin(tmp_path, monkeypatch):
    database = tmp_path / "legacy.db"
    database_url = f"sqlite:///{database}"
    engine = create_engine(database_url)
    create_legacy_database(engine)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setattr(cli, "getpass", lambda _prompt: "a secure migration password")
    settings = Settings(_env_file=None, app_data_dir=tmp_path, database_url=database_url)

    cli.create_admin(settings, "historical-owner")
    cli.migrate_legacy(settings, "historical-owner")

    with engine.connect() as connection:
        owner_id = connection.execute(text("SELECT id FROM users WHERE username = 'historical-owner'")).scalar_one()
        for table, record_id in (("conversations", "legacy-conversation"),
                                 ("attachments", "legacy-attachment"), ("memories", "legacy-memory")):
            actual_owner = connection.execute(text(f"SELECT user_id FROM {table} WHERE id = :id"), {"id": record_id}).scalar_one()
            assert actual_owner == owner_id
        assert connection.execute(text("SELECT content FROM messages WHERE id = 'legacy-message'")).scalar_one() == "Old message"
        assert {"skills", "conversation_skills"}.issubset(inspect(connection).get_table_names())

    for table in ("conversations", "attachments", "memories"):
        owner_column = next(column for column in inspect(engine).get_columns(table) if column["name"] == "user_id")
        assert owner_column["nullable"] is False
    cli.prepare_schema(settings)
    cli.create_admin(settings, "historical-owner")
    engine.dispose()


def test_legacy_data_requires_an_explicit_owner(tmp_path, monkeypatch):
    database = tmp_path / "legacy-unassigned.db"
    database_url = f"sqlite:///{database}"
    engine = create_engine(database_url)
    create_legacy_database(engine)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setattr(cli, "getpass", lambda _prompt: "a secure migration password")
    settings = Settings(_env_file=None, app_data_dir=tmp_path, database_url=database_url)

    cli.create_admin(settings, "historical-owner")
    with pytest.raises(SystemExit, match="choisissez explicitement un admin"):
        cli.migrate_legacy(settings, "")

    with engine.connect() as connection:
        assert connection.execute(text("SELECT user_id FROM conversations WHERE id = 'legacy-conversation'")).scalar_one() is None
    engine.dispose()
