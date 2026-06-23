import json
import time
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from backend.core import models
from backend.agendamento.crypto import decrypt_key
from backend.agendamento.slots import calcular_slots_livres
from backend.agendamento.adapters import gemini_adapter, groq_adapter, ollama_adapter
from backend.agendamento.google_sync import criar_evento_google, cancelar_evento_google
from backend.agendamento.adapters.base import LlmResponse

WINDOW_SIZE = 6


async def processar_mensagem(
    texto: str,
    config: models.AgendamentoConfig,
    client: models.Client,
    db: Session,
) -> str:
    db.add(models.ConversationMessage(
        config_id=config.id, client_id=client.id, role="user", content=texto,
    ))
    db.commit()

    historico = db.query(models.ConversationMessage).filter(
        models.ConversationMessage.config_id == config.id,
        models.ConversationMessage.client_id == client.id,
    ).order_by(models.ConversationMessage.criado_em.desc()).limit(WINDOW_SIZE).all()

    messages = [{"role": m.role, "content": m.content} for m in reversed(historico)]

    servicos = db.query(models.Service).filter(
        models.Service.config_id == config.id, models.Service.ativo == True,
    ).all()
    servicos_texto = "\n".join(
        f"- ID:{s.id} | {s.nome} | {s.duracao_minutos}min | R${s.preco:.2f}" for s in servicos
    ) if servicos else "Nenhum serviço cadastrado."

    system_prompt = (
        f"{config.catalogo_prompt or ''}\n\n"
        f"### Serviços disponíveis:\n{servicos_texto}\n\n"
        f"### Regras:\n"
        f"- Você é um assistente de agendamento via WhatsApp.\n"
        f"- NUNCA invente horários. Use a função buscar_horarios_disponiveis para consultar.\n"
        f"- Ao agendar, use pre_reservar_horario e peça confirmação ao cliente.\n"
        f"- Cliente pode cancelar ou reagendar usando as funções disponíveis.\n"
        f"- Seja objetivo e cordial. Responda em português.\n"
        f"- Data de hoje: {datetime.utcnow().strftime('%Y-%m-%d')}"
    )

    prioridades = json.loads(config.prioridade_llms or '["gemini","groq","ollama"]')
    providers_ativos = []
    for p in prioridades:
        if p == "gemini" and config.gemini_ativo:
            providers_ativos.append("gemini")
        elif p == "groq" and config.groq_ativo:
            providers_ativos.append("groq")
        elif p == "ollama" and config.ollama_ativo:
            providers_ativos.append("ollama")

    if not providers_ativos:
        return config.mensagem_contingencia or "Atendimento indisponível no momento."

    resposta = None
    provider_usado = None

    for provider in providers_ativos:
        start = time.time()
        llm_resp = await _call_provider(provider, messages, system_prompt, config)
        latency = int((time.time() - start) * 1000)

        db.add(models.LlmLog(
            config_id=config.id,
            provider=provider,
            model=llm_resp.model,
            status_code=200 if not llm_resp.error else 500,
            tokens_in=llm_resp.tokens_in,
            tokens_out=llm_resp.tokens_out,
            latency_ms=latency,
            erro=llm_resp.error,
        ))
        db.commit()

        if llm_resp.error:
            print(f"[agendamento] {provider} falhou: {llm_resp.error}")
            continue

        if llm_resp.tool_calls:
            result_text = await _execute_tool_calls(llm_resp.tool_calls, config, client, db)
            messages.append({"role": "assistant", "content": llm_resp.content or ""})
            messages.append({"role": "user", "content": f"[Resultado da função]: {result_text}"})

            start2 = time.time()
            llm_resp2 = await _call_provider(provider, messages, system_prompt, config)
            latency2 = int((time.time() - start2) * 1000)

            db.add(models.LlmLog(
                config_id=config.id, provider=provider, model=llm_resp2.model,
                status_code=200 if not llm_resp2.error else 500,
                tokens_in=llm_resp2.tokens_in, tokens_out=llm_resp2.tokens_out,
                latency_ms=latency2, erro=llm_resp2.error,
            ))
            db.commit()

            resposta = llm_resp2.content if not llm_resp2.error else result_text
        else:
            resposta = llm_resp.content

        provider_usado = provider
        break

    if not resposta:
        resposta = config.mensagem_contingencia or "Atendimento indisponível no momento."

    db.add(models.ConversationMessage(
        config_id=config.id, client_id=client.id, role="assistant",
        content=resposta, llm_provider=provider_usado,
    ))
    db.commit()

    return resposta


async def _call_provider(provider: str, messages: list, system_prompt: str, config) -> LlmResponse:
    if provider == "gemini":
        api_key = decrypt_key(config.gemini_api_key)
        return await gemini_adapter.call(messages, system_prompt, api_key)
    elif provider == "groq":
        api_key = decrypt_key(config.groq_api_key)
        return await groq_adapter.call(messages, system_prompt, api_key)
    elif provider == "ollama":
        return await ollama_adapter.call(
            messages, system_prompt, config.ollama_url or "http://localhost:11434",
            config.ollama_model or "llama3",
        )
    return LlmResponse(error=f"Provider desconhecido: {provider}")


async def _execute_tool_calls(tool_calls, config, client, db) -> str:
    results = []
    for tc in tool_calls:
        name = tc.name
        args = tc.arguments

        if name == "buscar_horarios_disponiveis":
            data_str = args.get("data", "")
            service_id = args.get("service_id", 0)
            try:
                dia = datetime.strptime(data_str, "%Y-%m-%d").date()
                slots = calcular_slots_livres(config.id, service_id, dia, db)
                if slots:
                    results.append(f"Horários disponíveis em {data_str}: {', '.join(slots)}")
                else:
                    results.append(f"Nenhum horário disponível em {data_str}.")
            except Exception as e:
                results.append(f"Erro ao buscar horários: {str(e)}")

        elif name == "pre_reservar_horario":
            service_id = args.get("service_id", 0)
            data_hora_str = args.get("data_hora", "")
            try:
                data_hora = datetime.strptime(data_hora_str, "%Y-%m-%d %H:%M")
                existente = db.query(models.Appointment).filter(
                    models.Appointment.config_id == config.id,
                    models.Appointment.data_hora == data_hora,
                    models.Appointment.status.in_(["confirmado", "pre_reservado"]),
                ).first()

                if existente and existente.status == "pre_reservado" and existente.expires_at and existente.expires_at < datetime.utcnow():
                    existente.status = "expirado"
                    db.commit()
                    existente = None

                if existente:
                    results.append("Este horário já está ocupado. Sugira outro horário ao cliente.")
                else:
                    appt = models.Appointment(
                        config_id=config.id, client_id=client.id, service_id=service_id,
                        data_hora=data_hora, status="pre_reservado",
                        expires_at=datetime.utcnow() + timedelta(minutes=5),
                    )
                    db.add(appt)
                    db.commit()
                    db.refresh(appt)

                    servico = db.query(models.Service).filter(models.Service.id == service_id).first()
                    nome_servico = servico.nome if servico else "Serviço"
                    results.append(
                        f"Pré-reserva criada (ID: {appt.id}). "
                        f"{nome_servico} em {data_hora.strftime('%d/%m/%Y às %H:%M')}. "
                        f"Peça ao cliente para confirmar. A reserva expira em 5 minutos."
                    )
            except Exception as e:
                results.append(f"Erro na pré-reserva: {str(e)}")

        elif name == "confirmar_agendamento":
            appt_id = args.get("appointment_id", 0)
            appt = db.query(models.Appointment).filter(
                models.Appointment.id == appt_id,
                models.Appointment.config_id == config.id,
                models.Appointment.client_id == client.id,
            ).first()
            if not appt:
                results.append("Agendamento não encontrado.")
            elif appt.status != "pre_reservado":
                results.append(f"Agendamento não pode ser confirmado (status: {appt.status}).")
            elif appt.expires_at and appt.expires_at < datetime.utcnow():
                appt.status = "expirado"
                db.commit()
                results.append("A pré-reserva expirou. O cliente precisa escolher um novo horário.")
            else:
                appt.status = "confirmado"
                appt.expires_at = None
                db.commit()
                await criar_evento_google(config, appt, db)
                results.append(f"Agendamento #{appt.id} confirmado com sucesso para {appt.data_hora.strftime('%d/%m/%Y às %H:%M')}!")

        elif name == "cancelar_agendamento":
            appt = db.query(models.Appointment).filter(
                models.Appointment.config_id == config.id,
                models.Appointment.client_id == client.id,
                models.Appointment.status.in_(["confirmado", "pre_reservado"]),
                models.Appointment.data_hora >= datetime.utcnow(),
            ).order_by(models.Appointment.data_hora).first()
            if not appt:
                results.append("Nenhum agendamento ativo encontrado para este cliente.")
            else:
                await cancelar_evento_google(config, appt, db)
                appt.status = "cancelado"
                db.commit()
                results.append(f"Agendamento de {appt.data_hora.strftime('%d/%m/%Y às %H:%M')} cancelado com sucesso.")

        elif name == "reagendar_agendamento":
            nova_str = args.get("nova_data_hora", "")
            try:
                nova_dt = datetime.strptime(nova_str, "%Y-%m-%d %H:%M")
                appt = db.query(models.Appointment).filter(
                    models.Appointment.config_id == config.id,
                    models.Appointment.client_id == client.id,
                    models.Appointment.status.in_(["confirmado", "pre_reservado"]),
                    models.Appointment.data_hora >= datetime.utcnow(),
                ).order_by(models.Appointment.data_hora).first()
                if not appt:
                    results.append("Nenhum agendamento ativo encontrado para reagendar.")
                else:
                    await cancelar_evento_google(config, appt, db)
                    appt.status = "cancelado"
                    novo = models.Appointment(
                        config_id=config.id, client_id=client.id, service_id=appt.service_id,
                        data_hora=nova_dt, status="pre_reservado",
                        expires_at=datetime.utcnow() + timedelta(minutes=5),
                    )
                    db.add(novo)
                    db.commit()
                    db.refresh(novo)
                    results.append(
                        f"Agendamento anterior cancelado. Nova pré-reserva (ID: {novo.id}) "
                        f"para {nova_dt.strftime('%d/%m/%Y às %H:%M')}. Peça confirmação ao cliente."
                    )
            except Exception as e:
                results.append(f"Erro ao reagendar: {str(e)}")
        else:
            results.append(f"Função '{name}' não reconhecida.")

    return " | ".join(results)
