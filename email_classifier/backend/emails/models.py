from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from backend.core.database import Base


class ContaEmail(Base):
    __tablename__ = "contas_email"

    id           = Column(Integer, primary_key=True, index=True)
    user_id      = Column(Integer, nullable=False, index=True)
    nome         = Column(String, nullable=False)          # apelido ex: "Gmail RH"
    provider     = Column(String, default="gmail")         # gmail | outlook | other
    email        = Column(String, nullable=False)
    password_enc = Column(String, nullable=False)
    imap_server  = Column(String, nullable=False)
    imap_port    = Column(Integer, default=993)
    ativo        = Column(Integer, default=1)               # 1=ativo 0=inativo
    criado_em    = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class EmailExtraido(Base):
    __tablename__ = "emails_extraidos"
    __table_args__ = (UniqueConstraint("message_id", name="uq_email_message_id"),)

    id               = Column(Integer, primary_key=True, index=True)
    message_id       = Column(String, unique=True, nullable=False, index=True)
    conta_id         = Column(Integer, nullable=True, index=True)   # qual conta originou
    user_id          = Column(Integer, nullable=False, index=True)
    remetente        = Column(String)
    assunto          = Column(String)
    corpo            = Column(Text)
    data_recebimento = Column(DateTime)
    categoria        = Column(String)
    subcategoria     = Column(String)
    sla              = Column(String)
    gerencial        = Column(String, default="nao")
    status           = Column(String, default="novo")      # novo | classificado | nao_classificado | tratado | ignorado
    criado_em        = Column(DateTime, default=lambda: datetime.now(timezone.utc))
