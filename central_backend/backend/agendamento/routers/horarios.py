from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user

router = APIRouter(prefix="/agendamento", tags=["Agendamento - Horários"])


def _get_config(user_id: int, db: Session) -> models.AgendamentoConfig:
    config = db.query(models.AgendamentoConfig).filter(
        models.AgendamentoConfig.user_id == user_id
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada.")
    return config


@router.get("/horarios", response_model=List[schemas.HorarioFuncionamentoResponse])
def listar_horarios(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = _get_config(current_user.id, db)
    return db.query(models.HorarioFuncionamento).filter(
        models.HorarioFuncionamento.config_id == config.id
    ).order_by(models.HorarioFuncionamento.dia_semana).all()


@router.post("/horarios", response_model=List[schemas.HorarioFuncionamentoResponse])
def salvar_horarios(
    horarios: List[schemas.HorarioFuncionamentoCreate],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = _get_config(current_user.id, db)

    db.query(models.HorarioFuncionamento).filter(
        models.HorarioFuncionamento.config_id == config.id
    ).delete()

    novos = []
    for h in horarios:
        novo = models.HorarioFuncionamento(**h.model_dump(), config_id=config.id)
        db.add(novo)
        novos.append(novo)

    db.commit()
    for n in novos:
        db.refresh(n)
    return novos


@router.delete("/horarios/{horario_id}")
def deletar_horario(
    horario_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = _get_config(current_user.id, db)
    horario = db.query(models.HorarioFuncionamento).filter(
        models.HorarioFuncionamento.id == horario_id,
        models.HorarioFuncionamento.config_id == config.id,
    ).first()
    if not horario:
        raise HTTPException(status_code=404, detail="Horário não encontrado.")
    db.delete(horario)
    db.commit()
    return {"ok": True}
