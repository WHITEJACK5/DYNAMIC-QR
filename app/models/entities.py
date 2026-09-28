"""SQLAlchemy ORM entity declarations.

Column-for-column match of the original hand-written CREATE TABLE, which is
why nullable/server_default are kept exactly as they were: raw SQL paths and
the Alembic baseline (migrations/versions/0001_initial_schema.py) both depend
on that shape.

The directive requires a models *layer* (`app/models/`), so the declarations
live here and `app.models` re-exports them — every existing
`from app.models import Base, User, ...` keeps working unchanged.
"""
from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str | None] = mapped_column(String, nullable=True)
    # Legacy DDL used "DEFAULT 0" and left these nullable; raw SQL INSERTs from
    # the repositories rely on the server default, so keep both properties.
    is_premium: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0, server_default=text("0"))
    twofa_enabled: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0, server_default=text("0"))
    twofa_secret: Mapped[str | None] = mapped_column(String, nullable=True)
    reset_token: Mapped[str | None] = mapped_column(String, nullable=True)
    reset_expires: Mapped[str | None] = mapped_column(String, nullable=True)
    # Phase 4d: email verification. 0/1 like the other legacy flags, with a
    # server default so existing rows and raw INSERTs keep working.
    email_verified: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0, server_default=text("0"))
    verify_token: Mapped[str | None] = mapped_column(String, nullable=True)
    verify_expires: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (Index("idx_users_verify_token", "verify_token"),)

    qrcodes: Mapped[list["QRCode"]] = relationship(back_populates="user")


class Folder(Base):
    __tablename__ = "folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str | None] = mapped_column(String, nullable=True)


class QRCode(Base):
    __tablename__ = "qrcodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    folder_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("folders.id"), nullable=True
    )
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    type: Mapped[str | None] = mapped_column(String, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_dynamic: Mapped[int | None] = mapped_column(Integer, nullable=True)
    short_code: Mapped[str | None] = mapped_column(String, unique=True)
    fg_color: Mapped[str | None] = mapped_column(String, nullable=True)
    bg_color: Mapped[str | None] = mapped_column(String, nullable=True)
    gradient: Mapped[str | None] = mapped_column(String, nullable=True)
    pattern: Mapped[str | None] = mapped_column(String, nullable=True)
    eye_style: Mapped[str | None] = mapped_column(String, nullable=True)
    frame_text: Mapped[str | None] = mapped_column(String, nullable=True)
    frame_color: Mapped[str | None] = mapped_column(String, nullable=True)
    logo_path: Mapped[str | None] = mapped_column(String, nullable=True)
    has_password: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0, server_default=text("0"))
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    expiry_date: Mapped[str | None] = mapped_column(String, nullable=True)
    scan_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scan_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0, server_default=text("0"))
    created_at: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index("idx_qr_short", "short_code"),
        Index("idx_qr_user", "user_id"),
    )

    user: Mapped["User | None"] = relationship(back_populates="qrcodes")
    scans: Mapped[list["Scan"]] = relationship(back_populates="qrcode")


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    qr_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("qrcodes.id"), nullable=True
    )
    timestamp: Mapped[str | None] = mapped_column(String, nullable=True)
    ip: Mapped[str | None] = mapped_column(String, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    device: Mapped[str | None] = mapped_column(String, nullable=True)
    browser: Mapped[str | None] = mapped_column(String, nullable=True)
    os: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (Index("idx_scans_qr", "qr_id"),)

    qrcode: Mapped["QRCode | None"] = relationship(back_populates="scans")


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str | None] = mapped_column(String, nullable=True)
