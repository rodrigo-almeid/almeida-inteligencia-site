from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user

router = APIRouter(prefix="/agendamento", tags=["Agendamento - Clientes"])


def _get_config(user_id: int, db: Session) -> models.AgendamentoConfig:
    config = db.query(models.AgendamentoConfig).filter(
        models.AgendamentoConfig.user_id == user_id
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada.")
    return config


@router.get("/clients", response_model=List[schemas.ClientResponse])
def listar_clients(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = _get_config(current_user.id, db)
    return db.query(models.Client).filter(
        models.Client.config_id == config.id
    ).order_by(models.Client.criado_em.desc()).all()


@router.get("/clients/{client_id}")
def detalhe_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = _get_config(current_user.id, db)
    client = db.query(models.Client).filter(
        models.Client.id == client_id,
        models.Client.config_id == config.id,
    ).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")

    appointments = db.query(models.Appointment).filter(
        models.Appointment.client_id == client.id,
    ).order_by(models.Appointment.data_hora.desc()).limit(20).all()

    return {
        "id": client.id,
        "telefone": client.telefone,
        "nome": client.nome,
        "criado_em": client.criado_em,
        "agendamentos": [
            {
                "id": a.id,
                "data_hora": a.data_hora,
                "status": a.status,
                "service_id": a.service_id,
            }
            for a in appointments
        ],
    }
