from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user

router = APIRouter(prefix="/agendamento", tags=["Agendamento - Serviços"])


def _get_config(user_id: int, db: Session) -> models.AgendamentoConfig:
    config = db.query(models.AgendamentoConfig).filter(
        models.AgendamentoConfig.user_id == user_id
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada.")
    return config


@router.get("/servicos", response_model=List[schemas.ServiceResponse])
def listar_servicos(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = _get_config(current_user.id, db)
    return db.query(models.Service).filter(
        models.Service.config_id == config.id
    ).all()


@router.post("/servicos", response_model=schemas.ServiceResponse, status_code=201)
def criar_servico(
    payload: schemas.ServiceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = _get_config(current_user.id, db)
    servico = models.Service(**payload.model_dump(), config_id=config.id)
    db.add(servico)
    db.commit()
    db.refresh(servico)
    return servico


@router.put("/servicos/{servico_id}", response_model=schemas.ServiceResponse)
def atualizar_servico(
    servico_id: int,
    payload: schemas.ServiceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = _get_config(current_user.id, db)
    servico = db.query(models.Service).filter(
        models.Service.id == servico_id,
        models.Service.config_id == config.id,
    ).first()
    if not servico:
        raise HTTPException(status_code=404, detail="Serviço não encontrado.")

    for key, value in payload.model_dump().items():
        setattr(servico, key, value)

    db.commit()
    db.refresh(servico)
    return servico


@router.delete("/servicos/{servico_id}")
def deletar_servico(
    servico_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = _get_config(current_user.id, db)
    servico = db.query(models.Service).filter(
        models.Service.id == servico_id,
        models.Service.config_id == config.id,
    ).first()
    if not servico:
        raise HTTPException(status_code=404, detail="Serviço não encontrado.")
    db.delete(servico)
    db.commit()
    return {"ok": True}
