from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path

from passlib.context import CryptContext
from sqlalchemy import create_engine, Column, String
from sqlalchemy.orm import declarative_base, Session

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    api_key = Column(String, unique=True, nullable=False, index=True)
    role = Column(String, nullable=False, default="read")  # read or write
    created_at = Column(String, nullable=False)


@dataclass
class AuthUser:
    id: str
    username: str
    api_key: str
    role: str


_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def hash_password(password: str) -> str:
    return _pwd_ctx.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _pwd_ctx.verify(password, hashed)


def create_user(db: Session, username: str, password: str, role: str = "read") -> AuthUser:
    from ai_memory.core.models import new_id, utc_now_iso
    user = User(
        id=new_id("user"),
        username=username,
        password_hash=hash_password(password),
        api_key=_generate_api_key(),
        role=role,
        created_at=utc_now_iso(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return AuthUser(id=user.id, username=user.username, api_key=user.api_key, role=user.role)


def verify_api_key(db: Session, api_key: str) -> AuthUser | None:
    user = db.query(User).filter(User.api_key == api_key).first()
    if not user:
        return None
    return AuthUser(id=user.id, username=user.username, api_key=user.api_key, role=user.role)


def verify_credentials(db: Session, username: str, password: str) -> AuthUser | None:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return AuthUser(id=user.id, username=user.username, api_key=user.api_key, role=user.role)


def list_users(db: Session) -> list[AuthUser]:
    users = db.query(User).all()
    return [AuthUser(id=u.id, username=u.username, api_key=u.api_key[:8] + "***", role=u.role) for u in users]


def delete_user(db: Session, user_id: str) -> bool:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    db.delete(user)
    db.commit()
    return True


def regenerate_api_key(db: Session, user_id: str) -> str | None:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    user.api_key = _generate_api_key()
    db.commit()
    return user.api_key


def init_auth_db(db_path: Path) -> None:
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)


def get_db(db_path: Path):
    engine = create_engine(f"sqlite:///{db_path}")
    with Session(engine) as db:
        yield db
