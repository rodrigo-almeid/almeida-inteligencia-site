from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from backend.core import models
from backend.core.database import get_db
from backend.core.security import get_current_user
from backend.assistente.routers.webhook import processar_mensagem

router = APIRouter(prefix="/assistente/simulador", tags=["Assistente Virtual — Simulador"])


class SimuladorRequest(BaseModel):
    mensagem: str
    tipo: str = "text"


class SimuladorResponse(BaseModel):
    resposta: Optional[str]
    intencao: Optional[str] = None


@router.post("/chat", response_model=SimuladorResponse)
async def simular_chat(
    payload: SimuladorRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = db.query(models.AssistenteConfig).filter(
        models.AssistenteConfig.user_id == current_user.id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="Configure o assistente antes de usar o simulador.")

    from backend.assistente.gemini import detectar_intencao

    msg_fake = {
        "type": payload.tipo,
        "text": {"body": payload.mensagem},
        "from": f"simulador_{current_user.id}",
    }

    intencao = None
    if payload.tipo == "text" and payload.mensagem:
        try:
            intencao = await detectar_intencao(None, payload.mensagem, config)
        except Exception:
            pass

    try:
        resposta = await processar_mensagem(msg_fake, config, current_user, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar: {str(e)}")

    return SimuladorResponse(resposta=resposta, intencao=intencao)


@router.delete("/historico")
async def limpar_historico(
    current_user: models.User = Depends(get_current_user),
):
    from backend.assistente.gemini import historico
    key = f"simulador_{current_user.id}"
    if key in historico:
        del historico[key]
    return {"status": "ok"}
