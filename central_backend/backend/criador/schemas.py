from typing import List, Optional
from pydantic import BaseModel


class TranscricaoCreate(BaseModel):
    url: str
    idioma: str = "pt"
    model_size: str = "small"
    webhook_url: Optional[str] = None


class Segmento(BaseModel):
    inicio: float
    fim: float
    texto: str


class TranscricaoJobOut(BaseModel):
    job_id: str
    status: str
    canal: Optional[str] = None
    titulo_video: Optional[str] = None
    video_id: Optional[str] = None
    duracao_segundos: Optional[float] = None
    segmentos: Optional[List[Segmento]] = None
    arquivo_txt_url: Optional[str] = None
    arquivo_srt_url: Optional[str] = None
    arquivo_sugestoes_url: Optional[str] = None
    erro: Optional[str] = None

    model_config = {"from_attributes": True}
