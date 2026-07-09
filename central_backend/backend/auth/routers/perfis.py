from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List

from backend.core import models
from backend.core.database import get_db
from backend.core.security import get_current_user

router = APIRouter(tags=["Perfis"])


class AtribuirPerfilRequest(BaseModel):
    email: str
    perfis: List[str]


@router.get("/me/perfis", response_model=List[str])
def listar_meus_perfis(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    return [p.nome for p in user.perfis]


@router.post("/auth/perfis/atribuir")
def atribuir_perfis(
    body: AtribuirPerfilRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Desativado (2026-07-09) — não validava se current_user é admin, o que permitia
    qualquer usuário autenticado se auto-atribuir qualquer perfil do sistema. Reativar
    só depois de decidir o modelo de autorização certo (ex: exigir perfil 'admin' do
    Portal, como o SSO já sincroniza — ver auth.py). Lógica original no histórico do git."""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Endpoint temporariamente desativado — sistema de perfis em revisão.",
    )
