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
    user = db.query(models.User).filter(models.User.email == body.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    user.perfis.clear()
    for nome in body.perfis:
        perfil = db.query(models.Perfil).filter(models.Perfil.nome == nome).first()
        if not perfil:
            raise HTTPException(
                status_code=400,
                detail=f"Perfil '{nome}' não existe. Perfis válidos: dashboard, senhas, abastecimento, financeiro, games, credenciais",
            )
        user.perfis.append(perfil)
    db.commit()
    return {"mensagem": f"Perfis atribuídos a {body.email}", "perfis": body.perfis}
