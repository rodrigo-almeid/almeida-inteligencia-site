import json
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user

router = APIRouter(prefix="/assistente", tags=["Assistente Virtual"])


class ValidacaoRequest(BaseModel):
    evolution_url: Optional[str] = None
    evolution_api_key: Optional[str] = None
    evolution_instance: Optional[str] = None
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None


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

    if payload.evolution_url and payload.evolution_api_key and payload.evolution_instance:
        try:
            base = payload.evolution_url.rstrip("/")
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(
                    f"{base}/instance/connectionState/{payload.evolution_instance}",
                    headers={"apikey": payload.evolution_api_key},
                )
                if res.status_code == 200:
                    data = res.json()
                    state = data.get("instance", {}).get("state", data.get("state", "unknown"))
                    if state == "open":
                        resultados.append({"nome": "Evolution API", "ok": True, "mensagem": "Conectado ao WhatsApp"})
                    else:
                        resultados.append({"nome": "Evolution API", "ok": True, "mensagem": f"API acessível — WhatsApp: {state} (escaneie o QR Code)"})
                elif res.status_code == 404:
                    resultados.append({"nome": "Evolution API", "ok": False, "mensagem": f"Instância '{payload.evolution_instance}' não encontrada"})
                else:
                    resultados.append({"nome": "Evolution API", "ok": False, "mensagem": f"Erro {res.status_code}"})
        except Exception as e:
            resultados.append({"nome": "Evolution API", "ok": False, "mensagem": f"Erro de conexão: {str(e)}"})
    elif payload.evolution_url or payload.evolution_api_key or payload.evolution_instance:
        resultados.append({"nome": "Evolution API", "ok": False, "mensagem": "Preencha URL, API Key e Nome da Instância"})
    else:
        resultados.append({"nome": "Evolution API", "ok": False, "mensagem": "Não configurado"})

    return {"resultados": resultados, "todos_ok": all(r["ok"] for r in resultados)}


@router.get("/qrcode")
async def get_qrcode(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = db.query(models.AssistenteConfig).filter(
        models.AssistenteConfig.user_id == current_user.id
    ).first()

    if not config or not config.evolution_url:
        raise HTTPException(status_code=404, detail="Configure a Evolution API primeiro.")

    base = config.evolution_url.rstrip("/")
    instance = config.evolution_instance

    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(
            f"{base}/instance/connect/{instance}",
            headers={"apikey": config.evolution_api_key},
        )

    if not res.is_success:
        raise HTTPException(status_code=502, detail=f"Erro ao obter QR Code: {res.text}")

    return res.json()


@router.get("/connection-state")
async def get_connection_state(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = db.query(models.AssistenteConfig).filter(
        models.AssistenteConfig.user_id == current_user.id
    ).first()

    if not config or not config.evolution_url:
        return {"state": "disconnected"}

    base = config.evolution_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(
                f"{base}/instance/connectionState/{config.evolution_instance}",
                headers={"apikey": config.evolution_api_key},
            )
        if res.is_success:
            data = res.json()
            state = data.get("instance", {}).get("state", data.get("state", "unknown"))
            return {"state": state}
    except Exception:
        pass
    return {"state": "error"}


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
