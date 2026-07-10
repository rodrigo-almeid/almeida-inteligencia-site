"""Execução das tools de agendamento chamadas pelo llm_gateway — lógica movida
de backend/agendamento/llm_gateway.py sem alterar o comportamento interno,
mais as tools de agenda pessoal (marcar direto, sem passo de confirmação
separado, e editar o assunto de um compromisso já marcado)."""
from datetime import datetime, timedelta

from backend.core import models
from backend.agendamento.slots import calcular_slots_livres
from backend.agendamento.google_sync import criar_evento_google, cancelar_evento_google, atualizar_evento_google
from backend.assistente.adapters.base import ToolCall
from backend.assistente.agenda_actions import montar_resumo_agenda

NOMES_TOOLS = {
    "buscar_horarios_disponiveis", "pre_reservar_horario", "confirmar_agendamento",
    "cancelar_agendamento", "reagendar_agendamento", "consultar_agenda",
    "marcar_compromisso", "atualizar_compromisso",
}


async def executar(tool_call: ToolCall, config: models.AgendamentoConfig, client: models.Client, db) -> str:
    name = tool_call.name
    args = tool_call.arguments

    if name == "buscar_horarios_disponiveis":
        return _buscar_horarios(args, config, db)
    if name == "marcar_compromisso":
        return await _marcar_direto(args, config, client, db)
    if name == "atualizar_compromisso":
        return await _atualizar_assunto(args, config, client, db)
    if name == "pre_reservar_horario":
        return _pre_reservar(args, config, client, db)
    if name == "confirmar_agendamento":
        return await _confirmar(args, config, client, db)
    if name == "cancelar_agendamento":
        return await _cancelar(config, client, db)
    if name == "reagendar_agendamento":
        return await _reagendar(args, config, client, db)
    if name == "consultar_agenda":
        return montar_resumo_agenda(config, client, db)
    return f"Função '{name}' não reconhecida."


def _buscar_horarios(args, config, db) -> str:
    data_str = args.get("data", "")
    service_id = args.get("service_id", 0)
    try:
        dia = datetime.strptime(data_str, "%Y-%m-%d").date()
        slots = calcular_slots_livres(config.id, service_id, dia, db)
        if slots:
            return f"Horários disponíveis em {data_str}: {', '.join(slots)}"
        return f"Nenhum horário disponível em {data_str}."
    except Exception as e:
        return f"Erro ao buscar horários: {str(e)}"


def _achar_conflito(config, data_hora, db):
    """Compromisso confirmado/pré-reservado (não expirado) já ocupando esse horário exato."""
    existente = db.query(models.Appointment).filter(
        models.Appointment.config_id == config.id,
        models.Appointment.data_hora == data_hora,
        models.Appointment.status.in_(["confirmado", "pre_reservado"]),
    ).first()

    if existente and existente.status == "pre_reservado" and existente.expires_at and existente.expires_at < datetime.utcnow():
        existente.status = "expirado"
        db.commit()
        return None

    return existente


async def _marcar_direto(args, config, client, db) -> str:
    """Marca o compromisso já confirmado, sem passo de confirmação separado —
    reporta conflito de horário em vez de criar em cima de outro compromisso."""
    service_id = args.get("service_id", 0)
    data_hora_str = args.get("data_hora", "")
    descricao = args.get("descricao") or None

    try:
        data_hora = datetime.strptime(data_hora_str, "%Y-%m-%d %H:%M")
    except Exception:
        return "Não consegui entender a data/hora pedida."

    conflito = _achar_conflito(config, data_hora, db)
    if conflito:
        servico_conflito = db.query(models.Service).filter(models.Service.id == conflito.service_id).first()
        nome_conflito = servico_conflito.nome if servico_conflito else "um compromisso"
        return (
            f"Conflito de agenda: já existe {nome_conflito} marcado pra "
            f"{data_hora.strftime('%d/%m/%Y às %H:%M')}. Sugira outro horário."
        )

    servico = db.query(models.Service).filter(models.Service.id == service_id).first()
    nome_servico = servico.nome if servico else "Compromisso"

    appt = models.Appointment(
        config_id=config.id, client_id=client.id, service_id=service_id,
        data_hora=data_hora, status="confirmado", descricao=descricao,
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)

    await criar_evento_google(config, appt, db)

    texto = f"{nome_servico} marcado pra {data_hora.strftime('%d/%m/%Y às %H:%M')}."
    if descricao:
        texto += f" Assunto: {descricao}."
    return texto


async def _atualizar_assunto(args, config, client, db) -> str:
    """Atualiza a descrição/assunto de um compromisso já marcado, localizado
    por data/hora (ou o próximo compromisso ativo, se não especificado)."""
    descricao = args.get("descricao", "")
    data_hora_str = args.get("data_hora")

    query = db.query(models.Appointment).filter(
        models.Appointment.config_id == config.id,
        models.Appointment.client_id == client.id,
        models.Appointment.status.in_(["confirmado", "pre_reservado"]),
    )

    appt = None
    if data_hora_str:
        try:
            data_hora = datetime.strptime(data_hora_str, "%Y-%m-%d %H:%M")
            appt = query.filter(models.Appointment.data_hora == data_hora).first()
        except Exception:
            appt = None
    if not appt:
        appt = query.filter(models.Appointment.data_hora >= datetime.utcnow()).order_by(models.Appointment.data_hora).first()

    if not appt:
        return "Não encontrei nenhum compromisso pra atualizar o assunto."

    appt.descricao = descricao
    db.commit()

    await atualizar_evento_google(config, appt, db)

    servico = db.query(models.Service).filter(models.Service.id == appt.service_id).first()
    nome_servico = servico.nome if servico else "Compromisso"
    return f"Assunto de {nome_servico} ({appt.data_hora.strftime('%d/%m %H:%M')}) atualizado pra: {descricao}"


def _pre_reservar(args, config, client, db) -> str:
    service_id = args.get("service_id", 0)
    data_hora_str = args.get("data_hora", "")
    try:
        data_hora = datetime.strptime(data_hora_str, "%Y-%m-%d %H:%M")
        existente = _achar_conflito(config, data_hora, db)

        if existente:
            return "Este horário já está ocupado. Sugira outro horário."

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
        return (
            f"Pré-reserva criada. {nome_servico} em {data_hora.strftime('%d/%m/%Y às %H:%M')}. "
            f"Peça confirmação. A reserva expira em 5 minutos."
        )
    except Exception as e:
        return f"Erro na pré-reserva: {str(e)}"


async def _confirmar(args, config, client, db) -> str:
    appt_id = args.get("appointment_id", 0)
    appt = db.query(models.Appointment).filter(
        models.Appointment.id == appt_id,
        models.Appointment.config_id == config.id,
        models.Appointment.client_id == client.id,
    ).first()
    if not appt:
        return "Agendamento não encontrado."
    if appt.status != "pre_reservado":
        return f"Agendamento não pode ser confirmado (status: {appt.status})."
    if appt.expires_at and appt.expires_at < datetime.utcnow():
        appt.status = "expirado"
        db.commit()
        return "A pré-reserva expirou. Escolha um novo horário."

    appt.status = "confirmado"
    appt.expires_at = None
    db.commit()
    await criar_evento_google(config, appt, db)
    return f"Compromisso confirmado com sucesso para {appt.data_hora.strftime('%d/%m/%Y às %H:%M')}!"


async def _cancelar(config, client, db) -> str:
    appt = db.query(models.Appointment).filter(
        models.Appointment.config_id == config.id,
        models.Appointment.client_id == client.id,
        models.Appointment.status.in_(["confirmado", "pre_reservado"]),
        models.Appointment.data_hora >= datetime.utcnow(),
    ).order_by(models.Appointment.data_hora).first()
    if not appt:
        return "Nenhum agendamento ativo encontrado."

    await cancelar_evento_google(config, appt, db)
    appt.status = "cancelado"
    db.commit()
    return f"Agendamento de {appt.data_hora.strftime('%d/%m/%Y às %H:%M')} cancelado com sucesso."


async def _reagendar(args, config, client, db) -> str:
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
            return "Nenhum agendamento ativo encontrado para reagendar."

        conflito = _achar_conflito(config, nova_dt, db)
        if conflito:
            return f"Conflito de agenda: já existe algo marcado pra {nova_dt.strftime('%d/%m/%Y às %H:%M')}. Sugira outro horário."

        descricao_antiga = appt.descricao
        status_antigo = appt.status
        await cancelar_evento_google(config, appt, db)
        appt.status = "cancelado"

        novo = models.Appointment(
            config_id=config.id, client_id=client.id, service_id=appt.service_id,
            data_hora=nova_dt, status=status_antigo, descricao=descricao_antiga,
            expires_at=(datetime.utcnow() + timedelta(minutes=5)) if status_antigo == "pre_reservado" else None,
        )
        db.add(novo)
        db.commit()
        db.refresh(novo)

        if status_antigo == "confirmado":
            await criar_evento_google(config, novo, db)
            return f"Compromisso remarcado pra {nova_dt.strftime('%d/%m/%Y às %H:%M')}."
        return (
            f"Agendamento anterior cancelado. Nova pré-reserva para "
            f"{nova_dt.strftime('%d/%m/%Y às %H:%M')}. Peça confirmação."
        )
    except Exception as e:
        return f"Erro ao reagendar: {str(e)}"
