import json
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user
from backend.agendamento.crypto import encrypt_key, decrypt_key

router = APIRouter(prefix="/assistente", tags=["Assistente Virtual"])

GRAPH_API_VERSION = "v21.0"


class ValidacaoRequest(BaseModel):
    whatsapp_token: Optional[str] = None
    whatsapp_phone_id: Optional[str] = None
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
        if payload.whatsapp_token and payload.whatsapp_token == _mask_key(_decifrar_com_fallback(config.whatsapp_token)):
            payload.whatsapp_token = _decifrar_com_fallback(config.whatsapp_token)
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
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={payload.gemini_api_key}",
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
                    f"https://graph.facebook.com/{GRAPH_API_VERSION}/{payload.whatsapp_phone_id}",
                    headers={"Authorization": f"Bearer {payload.whatsapp_token}"},
                    params={"fields": "verified_name,display_phone_number"},
                )
                if res.status_code == 200:
                    data = res.json()
                    nome = data.get("verified_name") or data.get("display_phone_number") or "número"
                    resultados.append({"nome": "Meta WhatsApp", "ok": True, "mensagem": f"Conectado — {nome}"})
                elif res.status_code == 401:
                    resultados.append({"nome": "Meta WhatsApp", "ok": False, "mensagem": "Token de acesso inválido ou expirado"})
                elif res.status_code == 404:
                    resultados.append({"nome": "Meta WhatsApp", "ok": False, "mensagem": "Phone Number ID não encontrado"})
                else:
                    resultados.append({"nome": "Meta WhatsApp", "ok": False, "mensagem": f"Erro {res.status_code}"})
        except Exception as e:
            resultados.append({"nome": "Meta WhatsApp", "ok": False, "mensagem": f"Erro de conexão: {str(e)}"})
    elif payload.whatsapp_token or payload.whatsapp_phone_id:
        resultados.append({"nome": "Meta WhatsApp", "ok": False, "mensagem": "Preencha o Token de Acesso e o Phone Number ID"})
    else:
        resultados.append({"nome": "Meta WhatsApp", "ok": False, "mensagem": "Não configurado"})

    return {"resultados": resultados, "todos_ok": all(r["ok"] for r in resultados)}


@router.get("/ollama/modelos")
async def listar_modelos_ollama(
    url: str,
    current_user: models.User = Depends(get_current_user),
):
    """Proxeia /api/tags do servidor Ollama informado — evita CORS no navegador
    e mantém a URL do Ollama fora do JS exposto ao cliente."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(f"{url.rstrip('/')}/api/tags")
        if res.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Ollama retornou {res.status_code}")
        modelos = [m["name"] for m in res.json().get("models", [])]
        return {"modelos": modelos}
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Não foi possível conectar ao Ollama: {str(e)}")


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
    """Decripta um valor cifrado (api_key, whatsapp_token). Cai pro valor bruto
    se não for um token Fernet válido — cobre dado legado gravado em texto
    plano antes de o campo passar a ser cifrado."""
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
    data["whatsapp_token"] = _mask_key(_decifrar_com_fallback(data.get("whatsapp_token")))
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


def _serialize_whatsapp_token(payload_dict: dict, config=None) -> dict:
    """Cifra whatsapp_token se for um valor novo; preserva a cifra existente se
    o painel reenviou a versão mascarada sem o usuário ter alterado o campo."""
    if "whatsapp_token" in payload_dict and payload_dict["whatsapp_token"] is not None:
        valor = payload_dict["whatsapp_token"]
        if config and valor == _mask_key(_decifrar_com_fallback(config.whatsapp_token)):
            payload_dict["whatsapp_token"] = config.whatsapp_token
        else:
            payload_dict["whatsapp_token"] = encrypt_key(valor)
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
    data = _serialize_whatsapp_token(data)
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

    payload_dict = payload.model_dump()

    # Preserva a chave real quando o painel reenvia o valor mascarado (campo não editado)
    if payload.provedores_llm is not None:
        payload_dict["provedores_llm"] = _merge_provedores_secrets(config, payload.provedores_llm)

    data = _serialize_provedores(payload_dict, config)
    data = _serialize_whatsapp_token(data, config)
    for key, value in data.items():
        if value is not None:
            setattr(config, key, value)

    db.commit()
    db.refresh(config)
    return _config_to_response(config)
