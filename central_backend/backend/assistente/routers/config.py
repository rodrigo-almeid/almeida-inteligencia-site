import json
import os
import secrets
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user
from backend.agendamento.crypto import encrypt_key, decrypt_key

router = APIRouter(prefix="/assistente", tags=["Assistente Virtual"])

# Nome do serviço do central-backend na rede interna do Docker Compose — a Evolution API
# roda como container irmão e alcança o webhook direto por aí, sem depender do Cloudflare Tunnel.
CENTRAL_BACKEND_INTERNAL_URL = os.getenv("CENTRAL_BACKEND_INTERNAL_URL", "http://central-backend:8000")


async def _garantir_instance(base: str, api_key: str, instance: str, webhook_url: str):
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    webhook_payload = {
        "webhook": {
            "enabled": True,
            "url": webhook_url,
            "byEvents": False,
            "base64": False,
            "events": ["MESSAGES_UPSERT"],
        }
    }
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(f"{base}/instance/connectionState/{instance}", headers=headers)
        if res.status_code == 404:
            create_res = await client.post(
                f"{base}/instance/create",
                headers=headers,
                json={
                    "instanceName": instance,
                    "qrcode": True,
                    "integration": "WHATSAPP-BAILEYS",
                    **webhook_payload,
                },
            )
            if not create_res.is_success:
                raise HTTPException(status_code=502, detail=f"Erro ao criar instância na Evolution API: {create_res.text}")
        else:
            # Instância já existe — garante que o webhook está configurado (idempotente).
            try:
                webhook_res = await client.post(f"{base}/webhook/set/{instance}", headers=headers, json=webhook_payload)
                if not webhook_res.is_success:
                    print(f"[assistente] erro ao configurar webhook na Evolution API: {webhook_res.status_code} {webhook_res.text}")
            except Exception as e:
                print(f"[assistente] erro ao configurar webhook na Evolution API: {e}")


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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # O painel reexibe as chaves mascaradas (GET /assistente/config); se o usuário
    # clicar em "Validar" sem reescrever o campo, troca de volta pelo valor real
    # antes de testar — senão o teste roda literalmente com a máscara (ex: "AIza…7890"),
    # que nem é uma chave válida nem um valor ASCII válido em header HTTP.
    config = db.query(models.AssistenteConfig).filter(
        models.AssistenteConfig.user_id == current_user.id
    ).first()
    if config:
        if payload.evolution_api_key and payload.evolution_api_key == _mask_key(config.evolution_api_key):
            payload.evolution_api_key = config.evolution_api_key
        chave_gemini_atual = _chave_atual_provedor(config, "gemini")
        if payload.gemini_api_key and payload.gemini_api_key == _mask_key(chave_gemini_atual):
            payload.gemini_api_key = chave_gemini_atual
        chave_groq_atual = _chave_atual_provedor(config, "groq")
        if payload.groq_api_key and payload.groq_api_key == _mask_key(chave_groq_atual):
            payload.groq_api_key = chave_groq_atual

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

    if not config.webhook_secret:
        config.webhook_secret = secrets.token_hex(16)
        db.commit()
        db.refresh(config)

    base = config.evolution_url.rstrip("/")
    instance = config.evolution_instance
    webhook_url = f"{CENTRAL_BACKEND_INTERNAL_URL}/assistente/webhook?secret={config.webhook_secret}"

    await _garantir_instance(base, config.evolution_api_key, instance, webhook_url)

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


@router.post("/desconectar")
async def desconectar_whatsapp(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Encerra a sessão do WhatsApp na Evolution API. Tenta logout normal; se a
    instância já não estiver conectada (sessão travada/derrubada pelo WhatsApp),
    apaga a instância pra parar o loop de reconexão automática — mesma limpeza
    manual feita via docker exec quando o WhatsApp derruba o device (conflict/device_removed)."""
    config = db.query(models.AssistenteConfig).filter(
        models.AssistenteConfig.user_id == current_user.id
    ).first()

    if not config or not config.evolution_url or not config.evolution_instance:
        raise HTTPException(status_code=404, detail="Configure a Evolution API primeiro.")

    base = config.evolution_url.rstrip("/")
    instance = config.evolution_instance
    headers = {"apikey": config.evolution_api_key}

    async with httpx.AsyncClient(timeout=15) as client:
        logout_res = await client.delete(f"{base}/instance/logout/{instance}", headers=headers)
        if logout_res.is_success:
            return {"status": "desconectado"}

        delete_res = await client.delete(f"{base}/instance/delete/{instance}", headers=headers)
        if delete_res.is_success:
            return {"status": "instancia_removida"}

        raise HTTPException(
            status_code=502,
            detail=f"Erro ao desconectar: {delete_res.status_code} {delete_res.text}",
        )


@router.post("/webhook/resync")
async def resync_webhook(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Reconfigura o webhook na Evolution API sem tocar na conexão (sem gerar QR Code).
    Existe pra não precisar passar pelo fluxo de 'Conectar WhatsApp' só pra atualizar
    o secret/URL do webhook — repetir esse fluxo à toa foi o que ajudou a instabilizar
    uma sessão real em produção."""
    config = db.query(models.AssistenteConfig).filter(
        models.AssistenteConfig.user_id == current_user.id
    ).first()

    if not config or not config.evolution_url:
        raise HTTPException(status_code=404, detail="Configure a Evolution API primeiro.")

    if not config.webhook_secret:
        config.webhook_secret = secrets.token_hex(16)
        db.commit()
        db.refresh(config)

    base = config.evolution_url.rstrip("/")
    webhook_url = f"{CENTRAL_BACKEND_INTERNAL_URL}/assistente/webhook?secret={config.webhook_secret}"
    await _garantir_instance(base, config.evolution_api_key, config.evolution_instance, webhook_url)
    return {"status": "ok"}


def _mask_key(key: Optional[str]) -> Optional[str]:
    """Mascara uma chave sensível para exibição — só os 4 primeiros/últimos caracteres."""
    if not key:
        return None
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:4]}…{key[-4:]}"


def _provedores_atuais(config) -> list:
    """Lista de provedores (dicts) já salvos no banco, sem filtrar por 'ativo'."""
    if not config or not config.provedores_llm:
        return []
    try:
        raw = json.loads(config.provedores_llm)
        return raw if isinstance(raw, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _decifrar_com_fallback(valor: Optional[str]) -> Optional[str]:
    """Decripta uma api_key salva em provedores_llm. Cai pro valor bruto se não
    for um token Fernet válido — cobre linhas gravadas antes da chave passar a
    ser cifrada (dado legado em texto plano continua funcionando)."""
    if not valor:
        return valor
    try:
        return decrypt_key(valor)
    except Exception:
        return valor


def _mask_key_provedor(cifra: Optional[str]) -> Optional[str]:
    return _mask_key(_decifrar_com_fallback(cifra))


def _chave_atual_provedor(config, tipo: str) -> Optional[str]:
    """API key atualmente salva pra um tipo de provedor (já decifrada) — busca em
    provedores_llm primeiro, cai pro campo legado (gemini_api_key/groq_api_key) se não achar."""
    for p in _provedores_atuais(config):
        if p.get("tipo") == tipo and p.get("api_key"):
            return _decifrar_com_fallback(p.get("api_key"))
    if tipo == "gemini":
        return getattr(config, "gemini_api_key", None)
    if tipo == "groq":
        return getattr(config, "groq_api_key", None)
    return None


def _merge_provedores_secrets(config, novos_provedores: list) -> list:
    """Preserva a api_key real (cifrada) quando o valor recebido é a versão mascarada
    (ou seja, o painel reenviou o campo sem o usuário ter alterado a chave)."""
    existentes_por_tipo: dict = {}
    for p in _provedores_atuais(config):
        existentes_por_tipo.setdefault(p.get("tipo"), []).append(p)

    indices_usados: dict = {}
    resultado = []
    for np in novos_provedores:
        p = np.model_dump() if hasattr(np, "model_dump") else dict(np)
        tipo = p.get("tipo")
        idx = indices_usados.get(tipo, 0)
        candidatos = existentes_por_tipo.get(tipo, [])
        antigo = candidatos[idx] if idx < len(candidatos) else None
        indices_usados[tipo] = idx + 1
        if antigo and p.get("api_key") and p.get("api_key") == _mask_key_provedor(antigo.get("api_key")):
            p["api_key"] = antigo.get("api_key")
        resultado.append(p)
    return resultado


def _config_to_response(config):
    data = {c.name: getattr(config, c.name) for c in config.__table__.columns}
    data.pop("webhook_secret", None)
    data["evolution_api_key"] = _mask_key(data.get("evolution_api_key"))
    if data.get("provedores_llm"):
        try:
            provedores = json.loads(data["provedores_llm"])
            for p in provedores:
                if isinstance(p, dict) and p.get("api_key"):
                    p["api_key"] = _mask_key_provedor(p["api_key"])
            data["provedores_llm"] = provedores
        except (json.JSONDecodeError, TypeError):
            data["provedores_llm"] = None
    return schemas.AssistenteConfigResponse(**data)


def _serialize_provedores(payload_dict: dict, config=None) -> dict:
    """Serializa provedores_llm pra JSON, cifrando toda api_key que seja um valor
    novo (não o que já estava salvo — evita recifrar o que _merge_provedores_secrets
    já preservou como cifra existente)."""
    if "provedores_llm" in payload_dict and payload_dict["provedores_llm"] is not None:
        cifras_por_tipo: dict = {}
        for p in (_provedores_atuais(config) if config else []):
            cifras_por_tipo.setdefault(p.get("tipo"), []).append(p.get("api_key"))
        usados: dict = {}
        serializados = []
        for np in payload_dict["provedores_llm"]:
            item = np.model_dump() if hasattr(np, "model_dump") else dict(np)
            tipo = item.get("tipo")
            idx = usados.get(tipo, 0)
            usados[tipo] = idx + 1
            candidatas = cifras_por_tipo.get(tipo, [])
            cifra_atual = candidatas[idx] if idx < len(candidatas) else None
            api_key = item.get("api_key")
            if api_key and api_key != cifra_atual:
                item["api_key"] = encrypt_key(api_key)
            serializados.append(item)
        payload_dict["provedores_llm"] = json.dumps(serializados)
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
    config = models.AssistenteConfig(**data, user_id=current_user.id, webhook_secret=secrets.token_hex(16))
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

    payload_dict = payload.model_dump()

    # Preserva a chave real quando o painel reenvia o valor mascarado (campo não editado)
    if payload.provedores_llm is not None:
        payload_dict["provedores_llm"] = _merge_provedores_secrets(config, payload.provedores_llm)
    if payload_dict.get("evolution_api_key") == _mask_key(config.evolution_api_key):
        payload_dict["evolution_api_key"] = config.evolution_api_key

    data = _serialize_provedores(payload_dict, config)
    for key, value in data.items():
        if value is not None:
            setattr(config, key, value)

    if not config.webhook_secret:
        config.webhook_secret = secrets.token_hex(16)

    db.commit()
    db.refresh(config)
    return _config_to_response(config)
