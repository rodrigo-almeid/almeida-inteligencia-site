import uuid
from datetime import datetime

from sqlalchemy import Column, String, Float, Text, DateTime, Integer, ForeignKey
from sqlalchemy.orm import relationship

from backend.core.models import Base


class TranscricaoJob(Base):
    __tablename__ = "transcricao_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    url = Column(String, nullable=False)
    idioma = Column(String, default="pt")
    model_size = Column(String, default="small")
    status = Column(String, default="pendente", index=True)
    # pendente | baixando | transcrevendo | concluido | erro

    video_id = Column(String, nullable=True)
    canal = Column(String, nullable=True)
    titulo_video = Column(String, nullable=True)
    duracao_segundos = Column(Float, nullable=True)
    segmentos_json = Column(Text, nullable=True)
    arquivo_txt_url = Column(String, nullable=True)
    arquivo_srt_url = Column(String, nullable=True)
    sugestoes_json = Column(Text, nullable=True)
    arquivo_sugestoes_url = Column(String, nullable=True)
    erro = Column(Text, nullable=True)
    webhook_url = Column(String, nullable=True)

    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user = relationship("User")
