import secrets
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, true
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .base_prompt import BASE_USER_PROMPT


def uid() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class FamilyGroup(Base):
    __tablename__ = "family_groups"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100), default="Groupe familial")
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    members: Mapped[list["User"]] = relationship(back_populates="family_group", order_by="User.username", foreign_keys="User.family_group_id")


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    family_group_id: Mapped[str | None] = mapped_column(ForeignKey("family_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    family_group: Mapped[FamilyGroup | None] = relationship(back_populates="members", foreign_keys=[family_group_id], lazy="joined")
    system_prompt: Mapped[str] = mapped_column(Text, default=BASE_USER_PROMPT, server_default=BASE_USER_PROMPT)
    prompt_cache_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    auto_memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Invitation(Base):
    __tablename__ = "invitations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="Nouvelle conversation")
    model: Mapped[str] = mapped_column(String(200))
    theme: Mapped[str] = mapped_column(String(80), default="")
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    summary: Mapped[str] = mapped_column(Text, default="")
    summary_through: Mapped[int] = mapped_column(Integer, default=0)
    creativity: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    sampling_params: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    topic_space_id: Mapped[str | None] = mapped_column(ForeignKey("topic_spaces.id", ondelete="SET NULL"), nullable=True, index=True)
    topic_space: Mapped["TopicSpace | None"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")
    chat_sites: Mapped[list["ChatSite"]] = relationship(cascade="all, delete-orphan")
    skill_links: Mapped[list["ConversationSkill"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="ConversationSkill.position",
    )

    @property
    def skills(self) -> list["Skill"]:
        return [link.skill for link in self.skill_links]


class ChatSite(Base):
    """Private, immutable HTML snapshot attached to its source conversation."""
    __tablename__ = "chat_sites"
    __table_args__ = (UniqueConstraint("conversation_id", "input_hash", name="uq_chat_sites_input"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    scope: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    html_content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="message")
    deep_search_reports: Mapped[list["DeepSearchReport"]] = relationship(back_populates="message", cascade="all, delete-orphan")
    learn_reports: Mapped[list["LearnReport"]] = relationship(back_populates="message", cascade="all, delete-orphan")


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer)
    storage_name: Mapped[str] = mapped_column(String(100), unique=True)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    extraction: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True)
    message: Mapped[Message | None] = relationship(back_populates="attachments")


class Memory(Base):
    __tablename__ = "memories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Skill(Base):
    __tablename__ = "skills"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    prompt: Mapped[str] = mapped_column(Text)
    creativity: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    sampling_params: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    conversation_links: Mapped[list["ConversationSkill"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan",
    )


class ConversationSkill(Base):
    __tablename__ = "conversation_skills"
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint("conversation_id", "position", name="uq_conversation_skills_position"),)
    conversation: Mapped[Conversation] = relationship(back_populates="skill_links")
    skill: Mapped[Skill] = relationship(back_populates="conversation_links")


class GeneratedImage(Base):
    __tablename__ = "generated_images"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    aspect_ratio: Mapped[str] = mapped_column(String(16), default="1:1")
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer)
    storage_name: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class GeneratedSound(Base):
    __tablename__ = "generated_sounds"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    sound_type: Mapped[str] = mapped_column(String(30), default="sound_effect")
    prompt: Mapped[str] = mapped_column(Text)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    prompt_influence: Mapped[float | None] = mapped_column(Float, nullable=True)
    output_format: Mapped[str] = mapped_column(String(50), default="mp3_44100_128")
    loop: Mapped[bool] = mapped_column(Boolean, default=False)
    instrumental: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    model_id: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120), default="audio/mpeg")
    size: Mapped[int] = mapped_column(Integer)
    storage_name: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Blog(Base):
    __tablename__ = "blogs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    prompt: Mapped[str] = mapped_column(Text)
    auto_refresh: Mapped[bool] = mapped_column(Boolean, default=False)
    theme: Mapped[str] = mapped_column(String(50), default="sunset")
    categories: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["news"])
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    posts: Mapped[list["BlogPost"]] = relationship(
        back_populates="blog", cascade="all, delete-orphan", order_by="BlogPost.created_at.desc()"
    )


class BlogPost(Base):
    __tablename__ = "blog_posts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    blog_id: Mapped[str] = mapped_column(ForeignKey("blogs.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    blog: Mapped[Blog] = relationship(back_populates="posts")


class DeepSearchReport(Base):
    __tablename__ = "deep_search_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True)
    message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    topic: Mapped[str] = mapped_column(Text)
    markdown_content: Mapped[str] = mapped_column(Text)
    html_content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    message: Mapped[Message | None] = relationship(back_populates="deep_search_reports")


class LearnReport(Base):
    __tablename__ = "learn_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True)
    message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    topic: Mapped[str] = mapped_column(Text)
    markdown_content: Mapped[str] = mapped_column(Text)
    html_content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    message: Mapped[Message | None] = relationship(back_populates="learn_reports")


class AgentTeam(Base):
    __tablename__ = "agent_teams"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    mode: Mapped[str] = mapped_column(String(30), default="synthesis")
    agents: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class TopicSpace(Base):
    __tablename__ = "topic_spaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    icon: Mapped[str] = mapped_column(String(16), default="📌")
    topic_type: Mapped[str] = mapped_column(String(30), default="learning")  # learning, project, interest, personal
    objective: Mapped[str] = mapped_column(Text, default="")
    current_resume_context: Mapped[str] = mapped_column(Text, default="")
    suggested_next_step: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="topic_space")
    memories: Mapped[list["TopicMemory"]] = relationship(back_populates="topic_space", cascade="all, delete-orphan", order_by="TopicMemory.created_at.desc()")
    events: Mapped[list["TopicEvent"]] = relationship(back_populates="topic_space", cascade="all, delete-orphan", order_by="TopicEvent.created_at.desc()")
    resources: Mapped[list["TopicResource"]] = relationship(back_populates="topic_space", cascade="all, delete-orphan", order_by="TopicResource.created_at.desc()")


class TopicResource(Base):
    __tablename__ = "topic_resources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    topic_space_id: Mapped[str] = mapped_column(ForeignKey("topic_spaces.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    resource_type: Mapped[str] = mapped_column(String(30), default="link")  # link, document, note
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    topic_space: Mapped[TopicSpace] = relationship(back_populates="resources")


class TopicMemory(Base):
    __tablename__ = "topic_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    topic_space_id: Mapped[str] = mapped_column(ForeignKey("topic_spaces.id", ondelete="CASCADE"), index=True)
    fact: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50), default="general")
    status: Mapped[str] = mapped_column(String(30), default="discussed")  # discussed, in_progress, needs_review, provisional_mastery, validated
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source_message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True)
    user_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    topic_space: Mapped[TopicSpace] = relationship(back_populates="memories")


class TopicEvent(Base):
    __tablename__ = "topic_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    topic_space_id: Mapped[str] = mapped_column(ForeignKey("topic_spaces.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))  # exercise_result, decision_taken, topic_introduced, session_recap
    title: Mapped[str] = mapped_column(String(200))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    topic_space: Mapped[TopicSpace] = relationship(back_populates="events")


def short_token() -> str:
    return secrets.token_urlsafe(12)


class WebPage(Base):
    __tablename__ = "web_pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="Page Web cLAIr")
    slug: Mapped[str] = mapped_column(String(200), default="page-web")
    public_token: Mapped[str] = mapped_column(String(32), unique=True, index=True, default=short_token)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    user: Mapped["User"] = relationship()
    versions: Mapped[list["WebPageVersion"]] = relationship(
        back_populates="page", cascade="all, delete-orphan", order_by="WebPageVersion.version_number.desc()"
    )


class WebPageVersion(Base):
    __tablename__ = "web_page_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    page_id: Mapped[str] = mapped_column(ForeignKey("web_pages.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    prompt_used: Mapped[str] = mapped_column(Text, default="")
    html_content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    page: Mapped[WebPage] = relationship(back_populates="versions")






