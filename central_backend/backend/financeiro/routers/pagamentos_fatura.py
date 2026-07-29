from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user, require_perfil

router = APIRouter(
    prefix="/pagamentos-fatura",
    tags=["Pagamentos Parciais de Fatura"],
    dependencies=[Depends(require_perfil("automacao_financeira"))],
)


@router.get("/", response_model=List[schemas.PagamentoFaturaResponse])
def listar_pagamentos(
    fatura_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.PagamentoFatura)
        .filter(
            models.PagamentoFatura.fatura_id == fatura_id,
            models.PagamentoFatura.user_id == current_user.id,
        )
        .order_by(models.PagamentoFatura.data_pagamento)
        .all()
    )


@router.post("/", response_model=schemas.PagamentoFaturaResponse, status_code=status.HTTP_201_CREATED)
def registrar_pagamento(
    pagamento: schemas.PagamentoFaturaCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    fatura = db.query(models.FaturaCartao).filter(
        models.FaturaCartao.id == pagamento.fatura_id,
        models.FaturaCartao.user_id == current_user.id,
    ).first()
    if not fatura:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    if fatura.status == "fechada":
        raise HTTPException(status_code=400, detail="Fatura fechada — reabra para registrar pagamentos")

    novo = models.PagamentoFatura(**pagamento.model_dump(), user_id=current_user.id)
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


@router.delete("/{pagamento_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_pagamento(
    pagamento_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    pagamento = db.query(models.PagamentoFatura).filter(
        models.PagamentoFatura.id == pagamento_id,
        models.PagamentoFatura.user_id == current_user.id,
    ).first()
    if not pagamento:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")

    fatura = db.query(models.FaturaCartao).filter(
        models.FaturaCartao.id == pagamento.fatura_id
    ).first()
    if fatura and fatura.status == "fechada":
        raise HTTPException(status_code=400, detail="Fatura fechada — reabra para remover pagamentos")

    db.delete(pagamento)
    db.commit()
