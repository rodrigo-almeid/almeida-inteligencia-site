import json
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
    groq_api_key: Optional[str] = None
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None


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

    if payload.groq_api_key:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {payload.groq_api_key}", "Content-Type": "application/json"},
                    json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": "responda apenas: ok"}], "max_tokens": 5},
                )
                if res.status_code == 200:
                    resultados.append({"nome": "Groq", "ok": True, "mensagem": "API Key válida"})
                else:
                    resultados.append({"nome": "Groq", "ok": False, "mensagem": f"Erro {res.status_code}"})
        except Exception as e:
            resultados.append({"nome": "Groq", "ok": False, "mensagem": f"Erro de conexão: {str(e)}"})

    if payload.ollama_url:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(f"{payload.ollama_url.rstrip('/')}/api/tags")
                if res.status_code == 200:
                    models_list = [m["name"] for m in res.json().get("models", [])]
                    if payload.ollama_model and payload.ollama_model not in models_list:
                        resultados.append({"nome": "Ollama", "ok": False, "mensagem": f"Modelo '{payload.ollama_model}' não encontrado. Disponíveis: {', '.join(models_list[:5])}"})
                    else:
                        resultados.append({"nome": "Ollama", "ok": True, "mensagem": f"Conectado — {len(models_list)} modelo(s) disponível(is)"})
                else:
                    resultados.append({"nome": "Ollama", "ok": False, "mensagem": f"Erro {res.status_code}"})
        except Exception as e:
            resultados.append({"nome": "Ollama", "ok": False, "mensagem": f"Erro de conexão: {str(e)}"})

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


def _config_to_response(config):
    data = {c.name: getattr(config, c.name) for c in config.__table__.columns}
    if data.get("provedores_llm"):
        try:
            data["provedores_llm"] = json.loads(data["provedores_llm"])
        except (json.JSONDecodeError, TypeError):
            data["provedores_llm"] = None
    return schemas.AssistenteConfigResponse(**data)


def _serialize_provedores(payload_dict: dict) -> dict:
    if "provedores_llm" in payload_dict and payload_dict["provedores_llm"] is not None:
        payload_dict["provedores_llm"] = json.dumps(
            [p.model_dump() if hasattr(p, 'model_dump') else p for p in payload_dict["provedores_llm"]]
        )
    return payload_dict


@router.get("/config")
def get_config(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    config = db.query(models.AssistenteConfig).filter(
        models.AssistenteConfig.user_id == current_user.id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada. Crie uma primeiro.")

    return _config_to_response(config)


@router.post("/config", status_code=status.HTTP_201_CREATED)
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

    data = _serialize_provedores(payload.model_dump())
    config = models.AssistenteConfig(**data, user_id=current_user.id)
    db.add(config)
    db.commit()
    db.refresh(config)
    return _config_to_response(config)


@router.put("/config")
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

    data = _serialize_provedores(payload.model_dump())
    for key, value in data.items():
        if value is not None:
            setattr(config, key, value)

    db.commit()
    db.refresh(config)
    return _config_to_response(config)
