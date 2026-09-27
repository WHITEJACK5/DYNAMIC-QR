"""SQLAlchemy ORM models (Phase 3a) — column-for-column match of the
hand-written CREATE TABLE in app.py:init_db.

Introduces the ORM without switching app.py yet (Phase 3c rewires the
repositories). Alembic (Phase 3b) autogenerates its baseline from these
declarations, so the inline DDL can then be deleted. SQLite stays the
default dialect for local/CI; DATABASE_URL=postgresql:// switches the
engine and its pool (core/db.py).
"""
from sqlalchemy import ForeignKey, Integer, String, Text
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
    is_premium: Mapped[int] = mapped_column(Integer, default=0)
    twofa_enabled: Mapped[int] = mapped_column(Integer, default=0)
    twofa_secret: Mapped[str | None] = mapped_column(String, nullable=True)
    reset_token: Mapped[str | None] = mapped_column(String, nullable=True)
    reset_expires: Mapped[str | None] = mapped_column(String, nullable=True)

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
    has_password: Mapped[int] = mapped_column(Integer, default=0)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    expiry_date: Mapped[str | None] = mapped_column(String, nullable=True)
    scan_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scan_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[str | None] = mapped_column(String, nullable=True)

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
