from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user, require_perfil

router = APIRouter(
    prefix="/cartoes",
    tags=["Cartões"],
    dependencies=[Depends(require_perfil("automacao_financeira"))],
)


@router.post("/", response_model=schemas.CartaoResponse, status_code=status.HTTP_201_CREATED)
def criar_cartao(
    cartao: schemas.CartaoCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    novo = models.Cartao(**cartao.model_dump(), user_id=current_user.id)
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


@router.get("/", response_model=List[schemas.CartaoResponse])
def listar_cartoes(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Cartao)
        .filter(models.Cartao.user_id == current_user.id, models.Cartao.ativo == True)
        .order_by(models.Cartao.nome)
        .all()
    )


@router.put("/{cartao_id}", response_model=schemas.CartaoResponse)
def atualizar_cartao(
    cartao_id: int,
    dados: schemas.CartaoCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cartao = db.query(models.Cartao).filter(
        models.Cartao.id == cartao_id,
        models.Cartao.user_id == current_user.id,
    ).first()
    if not cartao:
        raise HTTPException(status_code=404, detail="Cartão não encontrado")
    for key, value in dados.model_dump().items():
        setattr(cartao, key, value)
    db.commit()
    db.refresh(cartao)
    return cartao


@router.delete("/{cartao_id}", status_code=status.HTTP_204_NO_CONTENT)
def desativar_cartao(
    cartao_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cartao = db.query(models.Cartao).filter(
        models.Cartao.id == cartao_id,
        models.Cartao.user_id == current_user.id,
    ).first()
    if not cartao:
        raise HTTPException(status_code=404, detail="Cartão não encontrado")
    cartao.ativo = False
    db.commit()
