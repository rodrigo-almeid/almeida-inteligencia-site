import asyncio
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional

from backend.core import models, schemas
from backend.core.database import get_db, SessionLocal
from backend.core.security import get_current_user

router = APIRouter(prefix="/agendamento", tags=["Agendamento - Appointments"])


def _get_config(user_id: int, db: Session) -> models.AgendamentoConfig:
    config = db.query(models.AgendamentoConfig).filter(
        models.AgendamentoConfig.user_id == user_id
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada.")
    return config


def _response(appt: models.Appointment, db: Session) -> dict:
    """Monta o dict de resposta com nome de cliente/serviço já resolvidos
    (evita N+1 requests no calendário do front pra cada evento renderizado)."""
    cliente = db.query(models.Client).filter(models.Client.id == appt.client_id).first()
    servico = db.query(models.Service).filter(models.Service.id == appt.service_id).first() if appt.service_id else None

    return {
        "id": appt.id,
        "data_hora": appt.data_hora,
        "status": appt.status,
        "expires_at": appt.expires_at,
        "lembrete_enviado": appt.lembrete_enviado,
        "google_event_id": appt.google_event_id,
        "descricao": appt.descricao,
        "duracao_minutos": appt.duracao_minutos,
        "criado_em": appt.criado_em,
        "config_id": appt.config_id,
        "client_id": appt.client_id,
        "service_id": appt.service_id,
        "cliente_nome": cliente.nome if cliente else None,
        "servico_nome": servico.nome if servico else None,
        "servico_duracao_minutos": servico.duracao_minutos if servico else None,
    }


@router.get("/appointments", response_model=List[schemas.AppointmentResponse])
def listar_appointments(
    data: Optional[str] = Query(None, description="YYYY-MM-DD — dia único"),
    inicio: Optional[str] = Query(None, description="YYYY-MM-DD — início do período (calendário)"),
    fim: Optional[str] = Query(None, description="YYYY-MM-DD — fim do período, exclusivo (calendário)"),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = _get_config(current_user.id, db)
    query = db.query(models.Appointment).filter(
        models.Appointment.config_id == config.id
    )

    if data:
        dia = datetime.strptime(data, "%Y-%m-%d")
        query = query.filter(and_(
            models.Appointment.data_hora >= dia,
            models.Appointment.data_hora < dia + timedelta(days=1),
        ))
    elif inicio and fim:
        query = query.filter(and_(
            models.Appointment.data_hora >= datetime.strptime(inicio, "%Y-%m-%d"),
            models.Appointment.data_hora < datetime.strptime(fim, "%Y-%m-%d"),
        ))

    if status:
        query = query.filter(models.Appointment.status == status)

    appts = query.order_by(models.Appointment.data_hora).all()
    return [_response(a, db) for a in appts]


@router.post("/appointments", response_model=schemas.AppointmentResponse, status_code=201)
async def criar_appointment(
    payload: schemas.AppointmentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Cria um compromisso manualmente pelo calendário. Agenda é pessoal (1
    dono), então o cliente é sempre o mesmo — reaproveita/cria o registro
    'Dono', igual o fluxo do WhatsApp já faz."""
    from backend.agendamento.google_sync import criar_evento_google
    from backend.assistente.llm_gateway import _get_or_create_client
    from backend.assistente.tools_agendamento import _achar_conflito

    config = _get_config(current_user.id, db)

    conflito = _achar_conflito(config, payload.data_hora, db)
    if conflito:
        raise HTTPException(status_code=409, detail="Já existe um compromisso marcado nesse horário.")

    cliente = _get_or_create_client(config, None, db)

    appt = models.Appointment(
        config_id=config.id, client_id=cliente.id, service_id=payload.service_id,
        data_hora=payload.data_hora, descricao=payload.descricao,
        duracao_minutos=payload.duracao_minutos, status=payload.status,
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)

    if appt.status == "confirmado":
        await criar_evento_google(config, appt, db)
        db.refresh(appt)

    return _response(appt, db)


@router.put("/appointments/{appointment_id}", response_model=schemas.AppointmentResponse)
async def atualizar_appointment(
    appointment_id: int,
    payload: schemas.AppointmentUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Edita um compromisso (assunto/serviço/duração/status) e reagenda
    (drag-and-drop / resize no calendário) — sincroniza com o Google Calendar
    quando o compromisso já tem um evento lá."""
    from backend.agendamento.google_sync import atualizar_evento_google
    from backend.assistente.tools_agendamento import _achar_conflito

    config = _get_config(current_user.id, db)
    appt = db.query(models.Appointment).filter(
        models.Appointment.id == appointment_id,
        models.Appointment.config_id == config.id,
    ).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")

    if payload.data_hora and payload.data_hora != appt.data_hora:
        conflito = _achar_conflito(config, payload.data_hora, db, excluir_id=appt.id)
        if conflito:
            raise HTTPException(status_code=409, detail="Já existe um compromisso marcado nesse horário.")
        appt.data_hora = payload.data_hora

    if payload.service_id is not None:
        appt.service_id = payload.service_id
    if payload.descricao is not None:
        appt.descricao = payload.descricao
    if payload.duracao_minutos is not None:
        appt.duracao_minutos = payload.duracao_minutos
    if payload.status is not None:
        appt.status = payload.status
        if payload.status == "confirmado":
            appt.expires_at = None

    db.commit()
    db.refresh(appt)

    await atualizar_evento_google(config, appt, db)

    return _response(appt, db)


@router.put("/appointments/{appointment_id}/status")
async def alterar_status(
    appointment_id: int,
    novo_status: str = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from backend.agendamento.google_sync import criar_evento_google, cancelar_evento_google

    config = _get_config(current_user.id, db)
    appt = db.query(models.Appointment).filter(
        models.Appointment.id == appointment_id,
        models.Appointment.config_id == config.id,
    ).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")

    appt.status = novo_status
    if novo_status == "confirmado":
        appt.expires_at = None
    db.commit()
    db.refresh(appt)

    if novo_status == "confirmado":
        await criar_evento_google(config, appt, db)
    elif novo_status == "cancelado":
        await cancelar_evento_google(config, appt, db)

    return {"ok": True, "status": appt.status}


@router.delete("/appointments/{appointment_id}")
async def deletar_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from backend.agendamento.google_sync import cancelar_evento_google

    config = _get_config(current_user.id, db)
    appt = db.query(models.Appointment).filter(
        models.Appointment.id == appointment_id,
        models.Appointment.config_id == config.id,
    ).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")
    await cancelar_evento_google(config, appt, db)
    db.delete(appt)
    db.commit()
    return {"ok": True}


@router.get("/appointments/slots")
def slots_disponiveis(
    data: str = Query(..., description="YYYY-MM-DD"),
    service_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from backend.agendamento.slots import calcular_slots_livres
    config = _get_config(current_user.id, db)
    dia = datetime.strptime(data, "%Y-%m-%d").date()
    slots = calcular_slots_livres(config.id, service_id, dia, db)
    return {"data": data, "service_id": service_id, "slots": slots}
