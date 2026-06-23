from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user

router = APIRouter(prefix="/agendamento", tags=["Agendamento - Appointments"])


def _get_config(user_id: int, db: Session) -> models.AgendamentoConfig:
    config = db.query(models.AgendamentoConfig).filter(
        models.AgendamentoConfig.user_id == user_id
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada.")
    return config


@router.get("/appointments", response_model=List[schemas.AppointmentResponse])
def listar_appointments(
    data: Optional[str] = Query(None, description="YYYY-MM-DD"),
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

    if status:
        query = query.filter(models.Appointment.status == status)

    return query.order_by(models.Appointment.data_hora).all()


@router.put("/appointments/{appointment_id}/status")
def alterar_status(
    appointment_id: int,
    novo_status: str = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
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
    return {"ok": True, "status": appt.status}


@router.delete("/appointments/{appointment_id}")
def deletar_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = _get_config(current_user.id, db)
    appt = db.query(models.Appointment).filter(
        models.Appointment.id == appointment_id,
        models.Appointment.config_id == config.id,
    ).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")
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
