import json
from typing import Optional
import httpx
from fastapi import APIRouter, Request, Response, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core import models
from backend.core.database import get_db
from backend.assistente.gemini import (
    chat, detectar_intencao, extrair_dados_nota, extrair_dados_gasto,
    humanizar_confirmacao, perguntar_campos_faltantes, complementar_dados,
    _gerar,
)
from backend.assistente.whatsapp import enviar_mensagem, baixar_midia
from backend.assistente import llm_gateway
from backend.assistente.finance_actions import (
    CAMPOS_OBRIGATORIOS, validar_registro, _get_pendente, _salvar_pendente, _limpar_pendente,
    salvar_registro_financeiro, salvar_compra_mercado_de_texto, _eh_compra_de_mercado,
    salvar_conta, salvar_conta_from_nota, salvar_compra_mercado, formatar_nota, processar_nota_fiscal,
    montar_resumo_financeiro,
)
from backend.assistente.agenda_actions import montar_resumo_agenda

router = APIRouter(prefix="/assistente", tags=["Assistente Virtual"])


def get_config_by_secret(secret: Optional[str], db: Session):
    """Autentica o webhook pelo segredo — a rota é pública (exposta pelo nginx),
    então não dá pra confiar em campos do próprio corpo da requisição (ex: instance)."""
    if not secret:
        return None
    return db.query(models.AssistenteConfig).filter(
        models.AssistenteConfig.webhook_secret == secret,
        models.AssistenteConfig.ativo == True
    ).first()


@router.post("/webhook")
async def webhook_receive(request: Request, secret: Optional[str] = None, db: Session = Depends(get_db)):
    body = await request.json()

    event = body.get("event")
    if event != "messages.upsert":
        return {"status": "ignored", "event": event}

    config = get_config_by_secret(secret, db)
    if not config:
        return {"status": "unauthorized"}

    data = body.get("data", {})
    key = data.get("key", {})
    from_me = key.get("fromMe", False)
    if from_me:
        print(f"[goku] mensagem ignorada (fromMe): remoteJid={key.get('remoteJid', '')!r}")
        return {"status": "ignored", "reason": "fromMe"}

    user = db.query(models.User).filter(models.User.id == config.user_id).first()

    remote_jid = key.get("remoteJid", "")
    from_number = remote_jid.split("@")[0]

    if config.numero_autorizado and from_number != config.numero_autorizado:
        print(f"[goku] número não autorizado: recebido={from_number!r} esperado={config.numero_autorizado!r}")
        return {"status": "unauthorized"}

    message = data.get("message", {})

    msg = _evolution_to_msg(message, from_number, data)

    try:
        reply = await processar_mensagem(msg, config, user, db)
        if reply:
            await enviar_mensagem(
                config.evolution_url, config.evolution_api_key,
                config.evolution_instance, from_number, reply
            )
    except Exception as e:
        print(f"[goku] ERRO: {type(e).__name__}: {e}")
        await enviar_mensagem(
            config.evolution_url, config.evolution_api_key,
            config.evolution_instance, from_number,
            "Desculpe, tive um problema. Tente novamente."
        )

    return {"status": "ok"}


def _evolution_to_msg(message: dict, from_number: str, data: dict) -> dict:
    if "imageMessage" in message:
        mime = message.get("imageMessage", {}).get("mimetype", "image/jpeg")
        return {
            "type": "image",
            "image": {"raw_data": data, "mime_type": mime},
            "from": from_number,
        }

    texto = (
        message.get("conversation")
        or message.get("extendedTextMessage", {}).get("text")
        or ""
    )
    return {
        "type": "text",
        "text": {"body": texto},
        "from": from_number,
    }


async def processar_mensagem(msg, config, user, db):
    """3 branches, nessa ordem de prioridade — imagem e pendente ficam FORA do
    tool-calling (são máquinas de estado determinísticas já testadas). Só a
    mensagem "fria" (sem pendente, sem imagem) passa pelo llm_gateway novo
    quando a flag usar_tool_calling está ligada."""
    tipo = msg.get("type")
    texto = msg.get("text", {}).get("body", "")

    if tipo == "image":
        raw_data = msg.get("image", {}).get("raw_data")
        mime = msg.get("image", {}).get("mime_type", "image/jpeg")
        if not raw_data:
            return "Não consegui acessar a imagem. Tente enviar novamente."
        try:
            buffer = await baixar_midia(
                config.evolution_url, config.evolution_api_key, config.evolution_instance, raw_data
            )
        except Exception as e:
            print(f"[goku] erro ao baixar mídia: {e}")
            return "Não consegui baixar a imagem. Tente enviar novamente."
        dados = await extrair_dados_nota(config.gemini_api_key, buffer, mime, config)

        if not dados or not dados.get("valor_total"):
            return "Não consegui identificar uma nota fiscal nessa imagem. Tente uma foto mais nítida."

        _limpar_pendente(user.id, db)
        return processar_nota_fiscal(dados, user, db)

    if not texto:
        return None

    pendente = _get_pendente(user.id, db)
    if pendente:
        return await _processar_com_pendente(pendente, texto, config, user, db)

    if config.usar_tool_calling:
        return await llm_gateway.processar_mensagem(texto, config, user, db)

    intencao = await detectar_intencao(config.gemini_api_key, texto, config)

    if intencao == "financeiro_consulta":
        return await consultar_financeiro(texto, user, db, config)

    if intencao == "agenda":
        return await consultar_agenda(texto, user, config, db)

    if intencao == "financeiro_registro":
        dados = await extrair_dados_gasto(config.gemini_api_key, texto, config)
        if not dados:
            return await chat(config.gemini_api_key, msg.get("from"), texto, config)

        faltantes = validar_registro(dados)
        if not faltantes:
            salvar_registro_financeiro(dados, user, db)
            return await humanizar_confirmacao(dados, dados.get("forma_pagamento"), config)

        _salvar_pendente(user.id, dados, faltantes, db)
        return await perguntar_campos_faltantes(dados, faltantes, config)

    return await chat(config.gemini_api_key, msg.get("from"), texto, config)


async def _processar_com_pendente(pendente, texto, config, user, db):
    dados_atuais = json.loads(pendente.dados_json)
    campos_faltantes = json.loads(pendente.campos_faltantes)

    texto_lower = texto.strip().lower()
    if texto_lower in ("cancelar", "cancela", "deixa", "esquece", "para"):
        desc = dados_atuais.get("descricao", "registro")
        _limpar_pendente(user.id, db)
        return f"Beleza, cancelei o registro de *{desc}*! 👍"

    novos = await complementar_dados(dados_atuais, campos_faltantes, texto, config)

    if not novos:
        intencao = await detectar_intencao(config.gemini_api_key, texto, config)
        if intencao in ("financeiro_consulta", "financeiro_registro", "agenda"):
            desc = dados_atuais.get("descricao", "registro")
            return (
                f"Ei, você ainda tem o registro de *{desc}* pendente. "
                "Quer cancelar e seguir com outra coisa? (responde 'cancelar' ou me manda o que falta)"
            )
        return await perguntar_campos_faltantes(dados_atuais, campos_faltantes, config)

    for k, v in novos.items():
        if v and v != "null":
            dados_atuais[k] = v

    faltantes = validar_registro(dados_atuais)
    if not faltantes:
        _limpar_pendente(user.id, db)
        salvar_registro_financeiro(dados_atuais, user, db)
        return await humanizar_confirmacao(dados_atuais, dados_atuais.get("forma_pagamento"), config)

    _salvar_pendente(user.id, dados_atuais, faltantes, db)
    return await perguntar_campos_faltantes(dados_atuais, faltantes, config)


async def consultar_financeiro(texto, user, db, config=None):
    dados_financeiros = montar_resumo_financeiro(user, db)

    nome = config.nome_assistente if config and config.nome_assistente else "Goku"
    prompt = (
        f"Você é o {nome}, assistente financeiro no WhatsApp. "
        f"O usuário perguntou: \"{texto}\"\n\n"
        f"Dados financeiros do mês atual:\n{dados_financeiros}\n"
        "Responda a pergunta do usuário de forma direta e natural, como um amigo. "
        "Use os dados acima para dar uma resposta precisa. "
        "Formate valores como R$ X.XX. Use emoji com moderação (1-2). "
        "Se o usuário perguntou sobre vencimentos de hoje e não tem nenhum, diga que está tranquilo. "
        "Seja breve — máximo 4-5 linhas."
    )

    messages = [{"role": "user", "content": prompt}]
    contents = [{"role": "user", "parts": [{"text": prompt}]}]

    try:
        return await _gerar(config, messages, contents)
    except Exception:
        return f"📊 Resumo do mês:\n{dados_financeiros}"


async def consultar_agenda(texto, user, config, db):
    """Responde perguntas sobre a agenda usando SOMENTE dados reais de
    Appointment — nunca inventa compromisso (bug real corrigido em
    2026-07-10: 'agenda' caía no chat() livre, que alucinava eventos)."""
    agendamento_config = llm_gateway._get_or_create_agendamento_config(user, db)
    cliente = llm_gateway._get_or_create_client(agendamento_config, config.numero_autorizado, db)
    resumo = montar_resumo_agenda(agendamento_config, cliente, db)

    nome = config.nome_assistente if config and config.nome_assistente else "Goku"
    prompt = (
        f"Você é o {nome}, assistente pessoal no WhatsApp. "
        f"O usuário perguntou: \"{texto}\"\n\n"
        f"Dados reais da agenda:\n{resumo}\n\n"
        "Responda usando SOMENTE os dados acima. NUNCA invente, sugira ou complete "
        "um compromisso que não esteja listado — se a lista estiver vazia, diga claramente "
        "que não há nada agendado. Seja breve, no máximo 3-4 linhas, tom de amigo."
    )

    messages = [{"role": "user", "content": prompt}]
    contents = [{"role": "user", "parts": [{"text": prompt}]}]

    try:
        return await _gerar(config, messages, contents)
    except Exception:
        return resumo
