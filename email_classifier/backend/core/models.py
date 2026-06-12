from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from backend.core.database import Base


class User(Base):
    __tablename__ = "users"

    id         = Column(Integer, primary_key=True, index=True)
    nome       = Column(String, nullable=False)
    email      = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    ativo      = Column(Boolean, default=True)
    criado_em  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
