import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user

router = APIRouter(prefix="/assistente", tags=["Assistente Virtual"])


class ValidacaoRequest(BaseModel):
    whatsapp_token: Optional[str] = None
    whatsapp_phone_id: Optional[str] = None
    gemini_api_key: Optional[str] = None


class ValidacaoItem(BaseModel):
    nome: str
    ok: bool
    mensagem: str


@router.post("/validar")
async def validar_configuracoes(
    payload: ValidacaoRequest,
    current_user: models.User = Depends(get_current_user)
):
    resultados = []

    if payload.gemini_api_key:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={payload.gemini_api_key}",
                    json={"contents": [{"role": "user", "parts": [{"text": "responda apenas: ok"}]}]},
                )
                if res.status_code == 200:
                    resultados.append({"nome": "Google Gemini", "ok": True, "mensagem": "API Key válida"})
                elif res.status_code == 400:
                    data = res.json()
                    resultados.append({"nome": "Google Gemini", "ok": False, "mensagem": data.get("error", {}).get("message", "API Key inválida")})
                else:
                    resultados.append({"nome": "Google Gemini", "ok": False, "mensagem": f"Erro {res.status_code}: API Key inválida ou sem permissão"})
        except Exception as e:
            resultados.append({"nome": "Google Gemini", "ok": False, "mensagem": f"Erro de conexão: {str(e)}"})
    else:
        resultados.append({"nome": "Google Gemini", "ok": False, "mensagem": "API Key não informada"})

    if payload.whatsapp_token and payload.whatsapp_phone_id:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(
                    f"https://graph.facebook.com/v21.0/{payload.whatsapp_phone_id}",
                    headers={"Authorization": f"Bearer {payload.whatsapp_token}"},
                )
                if res.status_code == 200:
                    data = res.json()
                    numero = data.get("display_phone_number", "")
                    resultados.append({"nome": "WhatsApp (Meta)", "ok": True, "mensagem": f"Conectado — número {numero}" if numero else "Token e Phone ID válidos"})
                else:
                    data = res.json()
                    msg = data.get("error", {}).get("message", "Token ou Phone ID inválido")
                    resultados.append({"nome": "WhatsApp (Meta)", "ok": False, "mensagem": msg})
        except Exception as e:
            resultados.append({"nome": "WhatsApp (Meta)", "ok": False, "mensagem": f"Erro de conexão: {str(e)}"})
    elif payload.whatsapp_token or payload.whatsapp_phone_id:
        resultados.append({"nome": "WhatsApp (Meta)", "ok": False, "mensagem": "Preencha Token e Phone ID"})
    else:
        resultados.append({"nome": "WhatsApp (Meta)", "ok": False, "mensagem": "Não configurado"})

    return {"resultados": resultados, "todos_ok": all(r["ok"] for r in resultados)}


@router.get("/config", response_model=schemas.AssistenteConfigResponse)
def get_config(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    config = db.query(models.AssistenteConfig).filter(
        models.AssistenteConfig.user_id == current_user.id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada. Crie uma primeiro.")

    return config


@router.post("/config", response_model=schemas.AssistenteConfigResponse, status_code=status.HTTP_201_CREATED)
def criar_config(
    payload: schemas.AssistenteConfigCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    existente = db.query(models.AssistenteConfig).filter(
        models.AssistenteConfig.user_id == current_user.id
    ).first()

    if existente:
        raise HTTPException(status_code=400, detail="Configuração já existe. Use PUT para atualizar.")

    config = models.AssistenteConfig(**payload.model_dump(), user_id=current_user.id)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@router.put("/config", response_model=schemas.AssistenteConfigResponse)
def atualizar_config(
    payload: schemas.AssistenteConfigCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    config = db.query(models.AssistenteConfig).filter(
        models.AssistenteConfig.user_id == current_user.id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada.")

    for key, value in payload.model_dump().items():
        if value is not None:
            setattr(config, key, value)

    db.commit()
    db.refresh(config)
    return config
