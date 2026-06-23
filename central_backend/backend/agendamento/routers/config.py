import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user
from backend.agendamento.crypto import encrypt_key, mask_key

router = APIRouter(prefix="/agendamento", tags=["Agendamento - Config"])


def _get_config(user_id: int, db: Session) -> models.AgendamentoConfig:
    config = db.query(models.AgendamentoConfig).filter(
        models.AgendamentoConfig.user_id == user_id
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada.")
    return config


def _config_to_response(config: models.AgendamentoConfig) -> dict:
    return {
        "id": config.id,
        "whatsapp_phone_id": config.whatsapp_phone_id,
        "whatsapp_verify_token": config.whatsapp_verify_token,
        "gemini_api_key_masked": mask_key(config.gemini_api_key) if config.gemini_api_key else None,
        "groq_api_key_masked": mask_key(config.groq_api_key) if config.groq_api_key else None,
        "ollama_url": config.ollama_url,
        "ollama_model": config.ollama_model,
        "prioridade_llms": config.prioridade_llms,
        "gemini_ativo": config.gemini_ativo,
        "groq_ativo": config.groq_ativo,
        "ollama_ativo": config.ollama_ativo,
        "catalogo_prompt": config.catalogo_prompt,
        "mensagem_midia_bloqueada": config.mensagem_midia_bloqueada,
        "mensagem_contingencia": config.mensagem_contingencia,
        "ativo": config.ativo,
        "user_id": config.user_id,
    }


@router.get("/config")
def get_config(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = _get_config(current_user.id, db)
    return _config_to_response(config)


@router.post("/config", status_code=status.HTTP_201_CREATED)
def criar_config(
    payload: schemas.AgendamentoConfigCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    existente = db.query(models.AgendamentoConfig).filter(
        models.AgendamentoConfig.user_id == current_user.id
    ).first()
    if existente:
        raise HTTPException(status_code=400, detail="Configuração já existe. Use PUT para atualizar.")

    data = payload.model_dump()
    if data.get("gemini_api_key"):
        data["gemini_api_key"] = encrypt_key(data["gemini_api_key"])
    if data.get("groq_api_key"):
        data["groq_api_key"] = encrypt_key(data["groq_api_key"])
    if data.get("whatsapp_token"):
        data["whatsapp_token"] = encrypt_key(data["whatsapp_token"])

    config = models.AgendamentoConfig(**data, user_id=current_user.id)
    db.add(config)
    db.commit()
    db.refresh(config)
    return _config_to_response(config)


@router.put("/config")
def atualizar_config(
    payload: schemas.AgendamentoConfigCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = _get_config(current_user.id, db)

    data = payload.model_dump()
    for key, value in data.items():
        if value is None:
            continue
        if key in ("gemini_api_key", "groq_api_key", "whatsapp_token") and value:
            value = encrypt_key(value)
        setattr(config, key, value)

    db.commit()
    db.refresh(config)
    return _config_to_response(config)


@router.post("/config/testar-llm")
async def testar_llm(
    payload: schemas.TestarLlmRequest,
    current_user: models.User = Depends(get_current_user),
):
    provider = payload.provider.lower()

    if provider == "gemini":
        if not payload.api_key:
            return {"ok": False, "mensagem": "API Key não informada"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={payload.api_key}",
                    json={"contents": [{"role": "user", "parts": [{"text": "Diga olá"}]}]},
                )
                if res.status_code == 200:
                    return {"ok": True, "mensagem": "Gemini conectado com sucesso"}
                return {"ok": False, "mensagem": f"Erro {res.status_code}: {res.json().get('error', {}).get('message', 'Falha')}"}
        except Exception as e:
            return {"ok": False, "mensagem": f"Erro de conexão: {str(e)}"}

    elif provider == "groq":
        if not payload.api_key:
            return {"ok": False, "mensagem": "API Key não informada"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {payload.api_key}", "Content-Type": "application/json"},
                    json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": "Diga olá"}], "max_tokens": 10},
                )
                if res.status_code == 200:
                    return {"ok": True, "mensagem": "Groq conectado com sucesso"}
                return {"ok": False, "mensagem": f"Erro {res.status_code}: {res.text[:200]}"}
        except Exception as e:
            return {"ok": False, "mensagem": f"Erro de conexão: {str(e)}"}

    elif provider == "ollama":
        url = payload.ollama_url or "http://localhost:11434"
        model = payload.ollama_model or "llama3"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.post(
                    f"{url.rstrip('/')}/api/generate",
                    json={"model": model, "prompt": "Diga olá", "stream": False},
                )
                if res.status_code == 200:
                    return {"ok": True, "mensagem": f"Ollama ({model}) conectado com sucesso"}
                return {"ok": False, "mensagem": f"Erro {res.status_code}: {res.text[:200]}"}
        except Exception as e:
            return {"ok": False, "mensagem": f"Erro de conexão: {str(e)}"}

    return {"ok": False, "mensagem": f"Provedor '{provider}' não reconhecido"}
