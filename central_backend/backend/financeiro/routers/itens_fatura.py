from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user, require_perfil

router = APIRouter(
    prefix="/itens-fatura",
    tags=["Itens de Fatura"],
    dependencies=[Depends(require_perfil("automacao_financeira"))],
)


def _recalcular_total(fatura_id: int, db: Session) -> float:
    return db.query(func.sum(models.ItemFatura.valor)).filter(
        models.ItemFatura.fatura_id == fatura_id
    ).scalar() or 0.0


@router.get("/", response_model=List[schemas.ItemFaturaResponse])
def listar_itens(
    fatura_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.ItemFatura)
        .filter(
            models.ItemFatura.fatura_id == fatura_id,
            models.ItemFatura.user_id == current_user.id,
        )
        .order_by(models.ItemFatura.data_compra)
        .all()
    )


@router.post("/", response_model=schemas.ItemFaturaResponse, status_code=status.HTTP_201_CREATED)
def criar_item(
    item: schemas.ItemFaturaCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    fatura = db.query(models.FaturaCartao).filter(
        models.FaturaCartao.id == item.fatura_id,
        models.FaturaCartao.user_id == current_user.id,
    ).first()
    if not fatura:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    if fatura.status == "fechada":
        raise HTTPException(status_code=400, detail="Fatura fechada — reabra para adicionar itens")

    novo_item = models.ItemFatura(**item.model_dump(), user_id=current_user.id)
    db.add(novo_item)
    db.flush()

    fatura.valor_total = _recalcular_total(fatura.id, db)
    db.commit()
    db.refresh(novo_item)
    return novo_item


@router.put("/{item_id}", response_model=schemas.ItemFaturaResponse)
def atualizar_item(
    item_id: int,
    dados: schemas.ItemFaturaUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = db.query(models.ItemFatura).filter(
        models.ItemFatura.id == item_id,
        models.ItemFatura.user_id == current_user.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    fatura = db.query(models.FaturaCartao).filter(
        models.FaturaCartao.id == item.fatura_id
    ).first()
    if fatura.status == "fechada":
        raise HTTPException(status_code=400, detail="Fatura fechada — reabra para editar itens")

    for key, value in dados.model_dump().items():
        setattr(item, key, value)
    db.flush()

    fatura.valor_total = _recalcular_total(fatura.id, db)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = db.query(models.ItemFatura).filter(
        models.ItemFatura.id == item_id,
        models.ItemFatura.user_id == current_user.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    fatura = db.query(models.FaturaCartao).filter(
        models.FaturaCartao.id == item.fatura_id
    ).first()
    if fatura.status == "fechada":
        raise HTTPException(status_code=400, detail="Fatura fechada — reabra para remover itens")

    fatura_id = item.fatura_id
    db.delete(item)
    db.flush()

    fatura.valor_total = _recalcular_total(fatura_id, db)
    db.commit()
