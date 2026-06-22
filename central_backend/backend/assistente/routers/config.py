from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user

router = APIRouter(prefix="/assistente", tags=["Assistente Virtual"])


@router.get("/config", response_model=schemas.AssistenteConfigResponse)
def get_config(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    config = db.query(models.AssistenteConfig).filter(
        models.AssistenteConfig.user_id == current_user.id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada. Crie uma primeiro.")

    return config


@router.post("/config", response_model=schemas.AssistenteConfigResponse, status_code=status.HTTP_201_CREATED)
def criar_config(
    payload: schemas.AssistenteConfigCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    existente = db.query(models.AssistenteConfig).filter(
        models.AssistenteConfig.user_id == current_user.id
    ).first()

    if existente:
        raise HTTPException(status_code=400, detail="Configuração já existe. Use PUT para atualizar.")

    config = models.AssistenteConfig(**payload.model_dump(), user_id=current_user.id)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@router.put("/config", response_model=schemas.AssistenteConfigResponse)
def atualizar_config(
    payload: schemas.AssistenteConfigCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    config = db.query(models.AssistenteConfig).filter(
        models.AssistenteConfig.user_id == current_user.id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada.")

    for key, value in payload.model_dump().items():
        if value is not None:
            setattr(config, key, value)

    db.commit()
    db.refresh(config)
    return config
