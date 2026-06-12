from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from backend.core import models
from backend.core.database import get_db
from backend.core.security import get_current_user

router = APIRouter(tags=["Perfis"])


@router.get("/me/perfis", response_model=List[str])
def listar_meus_perfis(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    return [p.nome for p in user.perfis]
