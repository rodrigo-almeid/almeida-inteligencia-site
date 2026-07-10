from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user

router = APIRouter(prefix="/agendamento", tags=["Agendamento - Config"])


def _get_config(user_id: int, db: Session) -> models.AgendamentoConfig:
    config = db.query(models.AgendamentoConfig).filter(
        models.AgendamentoConfig.user_id == user_id
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada.")
    return config


def _config_to_response(config: models.AgendamentoConfig) -> dict:
    return {
        "id": config.id,
        "catalogo_prompt": config.catalogo_prompt,
        "mensagem_midia_bloqueada": config.mensagem_midia_bloqueada,
        "mensagem_contingencia": config.mensagem_contingencia,
        "ativo": config.ativo,
        "google_calendar_ativo": getattr(config, "google_calendar_ativo", False) or False,
        "google_calendar_id": getattr(config, "google_calendar_id", None),
        "google_calendar_conectado": bool(getattr(config, "google_calendar_token", None)),
        "user_id": config.user_id,
    }


@router.get("/config")
def get_config(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = _get_config(current_user.id, db)
    return _config_to_response(config)


@router.post("/config", status_code=status.HTTP_201_CREATED)
def criar_config(
    payload: schemas.AgendamentoConfigCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    existente = db.query(models.AgendamentoConfig).filter(
        models.AgendamentoConfig.user_id == current_user.id
    ).first()
    if existente:
        raise HTTPException(status_code=400, detail="Configuração já existe. Use PUT para atualizar.")

    data = payload.model_dump()
    config = models.AgendamentoConfig(**data, user_id=current_user.id)
    db.add(config)
    db.commit()
    db.refresh(config)
    return _config_to_response(config)


@router.put("/config")
def atualizar_config(
    payload: schemas.AgendamentoConfigCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = _get_config(current_user.id, db)

    data = payload.model_dump()
    for key, value in data.items():
        if value is None:
            continue
        setattr(config, key, value)

    db.commit()
    db.refresh(config)
    return _config_to_response(config)
