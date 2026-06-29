from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user, require_perfil

router = APIRouter(
    prefix="/mercado",
    tags=["Mercado"],
    dependencies=[Depends(require_perfil("mercado"))]
)


@router.post("/compras", response_model=schemas.CompraResponse, status_code=status.HTTP_201_CREATED)
def criar_compra(
        payload: schemas.CompraCreate,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(get_current_user)
):
    if not payload.itens:
        raise HTTPException(status_code=400, detail="A compra deve ter ao menos um item")

    valor_total = sum(i.valor for i in payload.itens)

    compra = models.CompraSupermercado(
        data=payload.data,
        loja=payload.loja,
        forma_pagamento=payload.forma_pagamento,
        bandeira_vale=payload.bandeira_vale if payload.forma_pagamento == "vale_alimentacao" else None,
        valor_total=valor_total,
        user_id=current_user.id
    )
    db.add(compra)
    db.flush()

    for item in payload.itens:
        db.add(models.ItemCompra(
            nome=item.nome,
            valor=item.valor,
            categoria=item.categoria,
            compra_id=compra.id
        ))

    db.commit()
    db.refresh(compra)
    return compra


@router.get("/compras")
def listar_compras(
        mes: Optional[int] = None,
        ano: Optional[int] = None,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(get_current_user)
):
    query = db.query(models.CompraSupermercado).filter(
        models.CompraSupermercado.user_id == current_user.id
    )

    if mes and ano:
        prefixo = f"{ano}-{str(mes).zfill(2)}"
        query = query.filter(models.CompraSupermercado.data.like(f"{prefixo}%"))

    compras = query.order_by(models.CompraSupermercado.data.desc()).all()

    total_mes = sum(c.valor_total for c in compras)
    total_debito = sum(c.valor_total for c in compras if c.forma_pagamento == "debito")
    total_credito = sum(c.valor_total for c in compras if c.forma_pagamento == "credito")
    total_vale = sum(c.valor_total for c in compras if c.forma_pagamento == "vale_alimentacao")

    return {
        "compras": [schemas.CompraResponse.model_validate(c) for c in compras],
        "resumo": {
            "total_mes": round(total_mes, 2),
            "total_debito": round(total_debito, 2),
            "total_credito": round(total_credito, 2),
            "total_vale": round(total_vale, 2),
            "qtd_compras": len(compras)
        }
    }


@router.delete("/compras/{compra_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_compra(
        compra_id: int,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(get_current_user)
):
    compra = db.query(models.CompraSupermercado).filter(
        models.CompraSupermercado.id == compra_id,
        models.CompraSupermercado.user_id == current_user.id
    ).first()

    if not compra:
        raise HTTPException(status_code=404, detail="Compra não encontrada")

    db.delete(compra)
    db.commit()
