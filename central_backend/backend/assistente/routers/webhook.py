import json
import re
from typing import Optional
import httpx
from fastapi import APIRouter, Request, Response, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core import models
from backend.core.database import get_db
from backend.agendamento.crypto import decrypt_key
from backend.assistente.gemini import (
    chat, chat_bulma, detectar_intencao, extrair_dados_nota, extrair_dados_gasto,
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


def get_config_by_phone_id(phone_id: Optional[str], db: Session):
    if not phone_id:
        return None
    return db.query(models.AssistenteConfig).filter(
        models.AssistenteConfig.whatsapp_phone_id == phone_id,
        models.AssistenteConfig.ativo == True
    ).first()


@router.get("/webhook")
def webhook_verify(request: Request, db: Session = Depends(get_db)):
    """Handshake de verificação exigido pela Meta ao cadastrar a Callback URL."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode != "subscribe" or not token:
        raise HTTPException(status_code=403, detail="Verificação inválida")

    config = db.query(models.AssistenteConfig).filter(
        models.AssistenteConfig.whatsapp_verify_token == token,
        models.AssistenteConfig.ativo == True,
    ).first()

    if not config:
        raise HTTPException(status_code=403, detail="Token de verificação inválido")

    return Response(content=challenge, media_type="text/plain")


@router.post("/webhook")
async def webhook_receive(request: Request, db: Session = Depends(get_db)):
    body = await request.json()

    entry = (body.get("entry") or [{}])[0]
    changes = (entry.get("changes") or [{}])[0]
    value = changes.get("value", {})

    if "messages" not in value:
        return {"status": "ignored", "reason": "no messages"}

    phone_id = value.get("metadata", {}).get("phone_number_id")
    config = get_config_by_phone_id(phone_id, db)
    if not config:
        return {"status": "unauthorized"}

    message = value["messages"][0]
    from_number = message.get("from", "")

    if config.numero_autorizado and from_number != config.numero_autorizado:
        print(f"[goku] número não autorizado: recebido={from_number!r} esperado={config.numero_autorizado!r}")
        return {"status": "unauthorized"}

    user = db.query(models.User).filter(models.User.id == config.user_id).first()
    token = decrypt_key(config.whatsapp_token)
    msg = _meta_to_msg(message, from_number)

    try:
        reply = await processar_mensagem(msg, config, user, db)
        if reply:
            await enviar_mensagem(token, config.whatsapp_phone_id, from_number, reply)
    except Exception as e:
        print(f"[goku] ERRO: {type(e).__name__}: {e}")
        await enviar_mensagem(
            token, config.whatsapp_phone_id, from_number,
            "Desculpe, tive um problema. Tente novamente."
        )

    return {"status": "ok"}


def _meta_to_msg(message: dict, from_number: str) -> dict:
    if message.get("type") == "image":
        image = message.get("image", {})
        return {
            "type": "image",
            "image": {"media_id": image.get("id"), "mime_type": image.get("mime_type", "image/jpeg")},
            "from": from_number,
        }

    texto = message.get("text", {}).get("body", "")
    return {
        "type": "text",
        "text": {"body": texto},
        "from": from_number,
    }


def _eh_chamada_bulma(texto: str) -> bool:
    """Palavra-gatilho 'bulma' em qualquer lugar da mensagem (case-insensitive,
    palavra inteira) chaveia pra a persona de bate-papo — checada ANTES de
    pendente/tool-calling/intenção, então funciona mesmo com um registro
    financeiro pendente em aberto (fica salvo, retomado na próxima mensagem
    sem o gatilho)."""
    return bool(re.search(r"\bbulma\b", texto, re.IGNORECASE))


async def processar_mensagem(msg, config, user, db):
    """3 branches, nessa ordem de prioridade — imagem e pendente ficam FORA do
    tool-calling (são máquinas de estado determinísticas já testadas). Só a
    mensagem "fria" (sem pendente, sem imagem) passa pelo llm_gateway novo
    quando a flag usar_tool_calling está ligada."""
    tipo = msg.get("type")
    texto = msg.get("text", {}).get("body", "")

    if tipo == "text" and texto and config.bulma_ativo and _eh_chamada_bulma(texto):
        return await chat_bulma(msg.get("from"), texto, config)

    if tipo == "image":
        media_id = msg.get("image", {}).get("media_id")
        mime = msg.get("image", {}).get("mime_type", "image/jpeg")
        if not media_id:
            return "Não consegui acessar a imagem. Tente enviar novamente."
        try:
            token = decrypt_key(config.whatsapp_token)
            buffer = await baixar_midia(token, media_id)
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
        "que não há nada agendado. "
        "IMPORTANTE: você NÃO tem capacidade de marcar, confirmar, cancelar ou alterar nenhum "
        "compromisso nesta conversa — só de consultar o que já existe. Se o usuário pedir pra "
        "marcar algo, NUNCA diga 'vou marcar', 'confirma?' ou qualquer frase que sugira que a ação "
        "foi ou será feita — em vez disso, explique que essa função de marcar ainda não está "
        "disponível pra ele nesse modo de atendimento. Seja breve, no máximo 3-4 linhas, tom de amigo."
    )

    messages = [{"role": "user", "content": prompt}]
    contents = [{"role": "user", "parts": [{"text": prompt}]}]

    try:
        return await _gerar(config, messages, contents)
    except Exception:
        return resumo
