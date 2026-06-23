from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_

from backend.core import models

SLOT_GRANULARITY_MINUTES = 30


def calcular_slots_livres(config_id: int, service_id: int, dia: date, db: Session) -> list[str]:
    servico = db.query(models.Service).filter(
        models.Service.id == service_id,
        models.Service.config_id == config_id,
        models.Service.ativo == True,
    ).first()
    if not servico:
        return []

    dia_semana = dia.weekday()
    horario = db.query(models.HorarioFuncionamento).filter(
        models.HorarioFuncionamento.config_id == config_id,
        models.HorarioFuncionamento.dia_semana == dia_semana,
        models.HorarioFuncionamento.ativo == True,
    ).first()
    if not horario:
        return []

    h_inicio = datetime.strptime(horario.hora_inicio, "%H:%M")
    h_fim = datetime.strptime(horario.hora_fim, "%H:%M")

    slots_necessarios = max(1, (servico.duracao_minutos + SLOT_GRANULARITY_MINUTES - 1) // SLOT_GRANULARITY_MINUTES)

    todos_slots = []
    cursor = h_inicio
    while cursor + timedelta(minutes=SLOT_GRANULARITY_MINUTES) <= h_fim:
        todos_slots.append(cursor.strftime("%H:%M"))
        cursor += timedelta(minutes=SLOT_GRANULARITY_MINUTES)

    inicio_dia = datetime.combine(dia, datetime.min.time())
    fim_dia = inicio_dia + timedelta(days=1)
    agora = datetime.utcnow()

    ocupados = db.query(models.Appointment).filter(
        models.Appointment.config_id == config_id,
        models.Appointment.data_hora >= inicio_dia,
        models.Appointment.data_hora < fim_dia,
        models.Appointment.status.in_(["confirmado", "pre_reservado"]),
    ).all()

    ocupados_validos = []
    for a in ocupados:
        if a.status == "pre_reservado" and a.expires_at and a.expires_at < agora:
            continue
        svc = db.query(models.Service).filter(models.Service.id == a.service_id).first()
        dur = svc.duracao_minutos if svc else SLOT_GRANULARITY_MINUTES
        inicio = a.data_hora
        fim = inicio + timedelta(minutes=dur)
        ocupados_validos.append((inicio, fim))

    def slot_livre(idx: int) -> bool:
        for offset in range(slots_necessarios):
            si = idx + offset
            if si >= len(todos_slots):
                return False
            slot_dt = datetime.combine(dia, datetime.strptime(todos_slots[si], "%H:%M").time())
            slot_fim = slot_dt + timedelta(minutes=SLOT_GRANULARITY_MINUTES)
            if slot_fim > datetime.combine(dia, h_fim.time()):
                return False
            for oc_inicio, oc_fim in ocupados_validos:
                if slot_dt < oc_fim and slot_fim > oc_inicio:
                    return False
        fim_servico = datetime.combine(dia, datetime.strptime(todos_slots[idx], "%H:%M").time()) + timedelta(minutes=servico.duracao_minutos)
        if fim_servico > datetime.combine(dia, h_fim.time()):
            return False
        return True

    livres = []
    for i, slot in enumerate(todos_slots):
        slot_dt = datetime.combine(dia, datetime.strptime(slot, "%H:%M").time())
        if slot_dt <= agora and dia == agora.date():
            continue
        if slot_livre(i):
            livres.append(slot)

    return livres
