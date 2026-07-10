"""Orquestrador único de tool-calling do assistente — decide entre tools de
agendamento e financeiras usando os adapters nativos de cada provider (Gemini/
Groq/Ollama). Substitui backend/agendamento/llm_gateway.py, generalizado pra
cobrir os dois domínios com um só conjunto de credenciais (AssistenteConfig.
provedores_llm).

Ativado só quando AssistenteConfig.usar_tool_calling=True (ver routers/webhook.py)
— com a flag desligada, o roteamento legado (detectar_intencao) continua intocado."""
import time
from datetime import datetime
from sqlalchemy.orm import Session

from backend.core import models
from backend.assistente.adapters import gemini_adapter, groq_adapter, ollama_adapter
from backend.assistente.adapters.base import LlmResponse, AGENDAMENTO_TOOLS_SCHEMA, FINANCEIRO_TOOLS_SCHEMA
from backend.assistente.gemini import _get_provedores, _get, montar_system_prompt
from backend.assistente import tools_agendamento, tools_financeiro

WINDOW_SIZE = 6


def _get_or_create_agendamento_config(user: models.User, db: Session) -> models.AgendamentoConfig:
    """AgendamentoConfig guarda o catálogo/serviços/horários E ancora a memória
    de conversa (ConversationMessage/Client) do assistente unificado — é criada
    vazia/inativa na primeira mensagem se o usuário nunca configurou agendamento."""
    config = db.query(models.AgendamentoConfig).filter(
        models.AgendamentoConfig.user_id == user.id
    ).first()
    if not config:
        config = models.AgendamentoConfig(user_id=user.id, ativo=False)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def _get_or_create_client(agendamento_config: models.AgendamentoConfig, telefone: str, db: Session) -> models.Client:
    """Bot é pessoal (só numero_autorizado fala com ele) — 1 Client representa
    o próprio dono, reaproveitando o esquema de agendamento (Client/Appointment)."""
    telefone = telefone or "dono"
    client = db.query(models.Client).filter(
        models.Client.config_id == agendamento_config.id,
        models.Client.telefone == telefone,
    ).first()
    if not client:
        client = models.Client(config_id=agendamento_config.id, telefone=telefone, nome="Dono")
        db.add(client)
        db.commit()
        db.refresh(client)
    return client


def _montar_system_prompt(assistente_config, agendamento_config, db: Session) -> str:
    prompt = montar_system_prompt(assistente_config)

    if agendamento_config and agendamento_config.ativo:
        servicos = db.query(models.Service).filter(
            models.Service.config_id == agendamento_config.id, models.Service.ativo == True,
        ).all()

        def _linha_servico(s):
            preco_txt = f" | R${s.preco:.2f}" if s.preco is not None else ""
            return f"- ID:{s.id} | {s.nome} | {s.duracao_minutos}min{preco_txt}"

        servicos_texto = "\n".join(_linha_servico(s) for s in servicos) if servicos else "Nenhum tipo de compromisso cadastrado."

        prompt += (
            f"\n\n{agendamento_config.catalogo_prompt or ''}\n\n"
            f"### Agenda — tipos de compromisso disponíveis:\n{servicos_texto}\n\n"
            f"### Regras de agendamento:\n"
            f"- Só chame funções de agendamento quando o usuário pedir explicitamente pra marcar, "
            f"cancelar, reagendar ou consultar horário/compromisso. Numa saudação ou conversa geral "
            f"('oi', 'tudo bem?', etc.), NÃO chame nenhuma função — só responda normalmente.\n"
            f"- Se o pedido de horário/data não tiver ambiguidade nenhuma, NÃO precisa checar "
            f"buscar_horarios_disponiveis antes — pode chamar marcar_compromisso direto, que já valida "
            f"conflito sozinho. Só use buscar_horarios_disponiveis se o usuário pedir sugestões de horário "
            f"ou o pedido for vago (ex: 'marca pra essa semana').\n"
            f"- Pra marcar um compromisso já com pedido direto e claro, use SEMPRE marcar_compromisso — "
            f"ela já confirma na hora, sem precisar de um segundo passo. NÃO use pre_reservar_horario/"
            f"confirmar_agendamento pra isso (essas são só pro caso raro de o usuário pedir explicitamente "
            f"pra 'segurar' o horário antes de decidir).\n"
            f"- Se marcar_compromisso retornar conflito de agenda, avise o usuário e pergunte outro horário "
            f"— não invente nem force outro horário sem perguntar.\n"
            f"- Pra adicionar/mudar o assunto de um compromisso já marcado, use atualizar_compromisso.\n"
            f"- NUNCA mencione o ID/número interno de um compromisso pro usuário — fale só pelo nome e "
            f"horário (ex: 'sua reunião das 14h', não 'agendamento #7').\n"
            f"- Pode cancelar ou reagendar usando as funções disponíveis.\n"
            f"- Data de hoje: {datetime.utcnow().strftime('%Y-%m-%d')}"
        )

    prompt += (
        "\n\n### Finanças:\n"
        "- Para registrar um gasto/receita relatado pelo usuário, use a função registrar_gasto.\n"
        "- Para perguntas sobre saldo, gastos ou contas, use a função consultar_financas.\n"
    )
    return prompt


async def processar_mensagem(texto: str, assistente_config: models.AssistenteConfig, user: models.User, db: Session) -> str:
    agendamento_config = _get_or_create_agendamento_config(user, db)
    client = _get_or_create_client(agendamento_config, assistente_config.numero_autorizado, db)

    db.add(models.ConversationMessage(
        config_id=agendamento_config.id, client_id=client.id, role="user", content=texto,
    ))
    db.commit()

    historico = db.query(models.ConversationMessage).filter(
        models.ConversationMessage.config_id == agendamento_config.id,
        models.ConversationMessage.client_id == client.id,
    ).order_by(models.ConversationMessage.criado_em.desc()).limit(WINDOW_SIZE).all()
    messages = [{"role": m.role, "content": m.content} for m in reversed(historico)]

    tools_schema = list(FINANCEIRO_TOOLS_SCHEMA)
    if agendamento_config.ativo:
        tools_schema = AGENDAMENTO_TOOLS_SCHEMA + tools_schema

    system_prompt = _montar_system_prompt(assistente_config, agendamento_config, db)

    provedores = _get_provedores(assistente_config)

    resposta = None
    provider_usado = None

    for p in provedores:
        tipo = _get(p, "tipo")
        start = time.time()
        llm_resp = await _call_provider(tipo, p, messages, system_prompt, tools_schema)
        latency = int((time.time() - start) * 1000)

        db.add(models.LlmLog(
            config_id=agendamento_config.id, provider=tipo, model=llm_resp.model,
            status_code=200 if not llm_resp.error else 500,
            tokens_in=llm_resp.tokens_in, tokens_out=llm_resp.tokens_out,
            latency_ms=latency, erro=llm_resp.error,
        ))
        db.commit()

        if llm_resp.error:
            print(f"[assistente] {tipo} falhou: {llm_resp.error}")
            continue

        if llm_resp.tool_calls:
            result_text = await _execute_tool_calls(llm_resp.tool_calls, agendamento_config, client, user, db)
            messages.append({"role": "assistant", "content": llm_resp.content or ""})
            messages.append({"role": "user", "content": f"[Resultado da função]: {result_text}"})

            # Sem tools_schema aqui de propósito: essa 2ª chamada é só pra transformar
            # o resultado já executado em texto natural — reoferecer as tools deixava
            # o modelo tentado a chamar outra função em vez de responder em texto.
            start2 = time.time()
            llm_resp2 = await _call_provider(tipo, p, messages, system_prompt, None)
            latency2 = int((time.time() - start2) * 1000)

            db.add(models.LlmLog(
                config_id=agendamento_config.id, provider=tipo, model=llm_resp2.model,
                status_code=200 if not llm_resp2.error else 500,
                tokens_in=llm_resp2.tokens_in, tokens_out=llm_resp2.tokens_out,
                latency_ms=latency2, erro=llm_resp2.error,
            ))
            db.commit()

            if llm_resp2.error:
                print(f"[assistente] {tipo} falhou na 2ª chamada (humanização): {llm_resp2.error}")
            elif not llm_resp2.content:
                print(f"[assistente] {tipo} devolveu conteúdo vazio na 2ª chamada (sem erro) — "
                      f"tool_calls={llm_resp2.tool_calls!r}, usando texto cru da função como resposta")
            resposta = llm_resp2.content if (not llm_resp2.error and llm_resp2.content) else result_text
        else:
            resposta = llm_resp.content

        provider_usado = tipo
        break

    if not resposta:
        resposta = "Atendimento indisponível no momento."

    db.add(models.ConversationMessage(
        config_id=agendamento_config.id, client_id=client.id, role="assistant",
        content=resposta, llm_provider=provider_usado,
    ))
    db.commit()

    return resposta


async def _call_provider(tipo: str, p, messages: list, system_prompt: str, tools_schema: list) -> LlmResponse:
    if tipo == "gemini" and _get(p, "api_key"):
        return await gemini_adapter.call(messages, system_prompt, _get(p, "api_key"), tools_schema)
    if tipo == "groq" and _get(p, "api_key"):
        return await groq_adapter.call(messages, system_prompt, _get(p, "api_key"), tools_schema)
    if tipo == "ollama" and _get(p, "url"):
        return await ollama_adapter.call(
            messages, system_prompt, _get(p, "url"), _get(p, "modelo") or "llama3", tools_schema,
        )
    return LlmResponse(error=f"Provider inválido/sem credencial: {tipo}")


async def _execute_tool_calls(tool_calls, agendamento_config, client, user, db) -> str:
    results = []
    for tc in tool_calls:
        if tc.name in tools_agendamento.NOMES_TOOLS:
            results.append(await tools_agendamento.executar(tc, agendamento_config, client, db))
        elif tc.name in tools_financeiro.NOMES_TOOLS:
            results.append(await tools_financeiro.executar(tc, user, db))
        else:
            results.append(f"Função '{tc.name}' não reconhecida.")
    return " | ".join(results)
