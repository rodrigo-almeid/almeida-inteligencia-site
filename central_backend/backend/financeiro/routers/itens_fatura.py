import re
from fastapi import APIRouter, Depends, HTTPException, Query, status
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

_SUFIXO_PARCELA = re.compile(r'\s*\(\d+/\d+\)$')


def _recalcular_total(fatura_id: int, db: Session) -> float:
    return db.query(func.sum(models.ItemFatura.valor)).filter(
        models.ItemFatura.fatura_id == fatura_id
    ).scalar() or 0.0


def _criar_futuras(
    db: Session,
    fatura_origem: models.FaturaCartao,
    descricao_base: str,
    valor: float,
    data_compra,
    categoria_id,
    parcela_atual: int,
    total_parcelas: int,
    grupo_id: int,
    user_id: int,
):
    ano_ref = int(fatura_origem.mes_referencia[:4])
    mes_ref = int(fatura_origem.mes_referencia[5:7])

    for i in range(1, total_parcelas - parcela_atual + 1):
        mes_n = mes_ref + i
        ano_n = ano_ref
        while mes_n > 12:
            mes_n -= 12
            ano_n += 1

        fatura_n = db.query(models.FaturaCartao).filter(
            models.FaturaCartao.cartao_id == fatura_origem.cartao_id,
            models.FaturaCartao.mes_referencia == f"{ano_n}-{mes_n:02d}",
            models.FaturaCartao.user_id == user_id,
        ).first()

        if not fatura_n:
            fatura_n = models.FaturaCartao(
                cartao_id=fatura_origem.cartao_id,
                mes_referencia=f"{ano_n}-{mes_n:02d}",
                valor_total=0.0,
                status="aberta",
                user_id=user_id,
            )
            db.add(fatura_n)
            db.flush()

        parcela_n = parcela_atual + i
        db.add(models.ItemFatura(
            fatura_id=fatura_n.id,
            descricao=f"{descricao_base} ({parcela_n}/{total_parcelas})",
            valor=valor,
            data_compra=data_compra,
            categoria_id=categoria_id,
            parcela_atual=parcela_n,
            total_parcelas=total_parcelas,
            grupo_parcela_id=grupo_id,
            user_id=user_id,
        ))
        db.flush()
        fatura_n.valor_total = _recalcular_total(fatura_n.id, db)


def _cancelar_futuras(db: Session, grupo_id: int, apos_parcela: int, user_id: int):
    siblings = (
        db.query(models.ItemFatura)
        .filter(
            models.ItemFatura.grupo_parcela_id == grupo_id,
            models.ItemFatura.parcela_atual > apos_parcela,
            models.ItemFatura.user_id == user_id,
        )
        .all()
    )
    for s in siblings:
        fatura_s = db.query(models.FaturaCartao).filter(models.FaturaCartao.id == s.fatura_id).first()
        if fatura_s and fatura_s.status == "aberta":
            fid = s.fatura_id
            db.delete(s)
            db.flush()
            fatura_s.valor_total = _recalcular_total(fid, db)


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

    total = item.total_parcelas if (item.total_parcelas and item.total_parcelas > 1) else None
    parcela = item.parcela_atual or 1 if total else None
    desc_base = _SUFIXO_PARCELA.sub('', item.descricao).strip()
    descricao = f"{desc_base} ({parcela}/{total})" if total else item.descricao

    dados = item.model_dump()
    dados.update(descricao=descricao, parcela_atual=parcela, total_parcelas=total, grupo_parcela_id=None)

    novo = models.ItemFatura(**dados, user_id=current_user.id)
    db.add(novo)
    db.flush()

    if total:
        novo.grupo_parcela_id = novo.id
        db.flush()
        if parcela < total:
            _criar_futuras(db, fatura, desc_base, item.valor, item.data_compra,
                           item.categoria_id, parcela, total, novo.id, current_user.id)

    fatura.valor_total = _recalcular_total(fatura.id, db)
    db.commit()
    db.refresh(novo)
    return novo


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

    fatura = db.query(models.FaturaCartao).filter(models.FaturaCartao.id == item.fatura_id).first()
    if fatura.status == "fechada":
        raise HTTPException(status_code=400, detail="Fatura fechada — reabra para editar itens")

    old_grupo = item.grupo_parcela_id
    old_parcela = item.parcela_atual or 0

    new_total = dados.total_parcelas if (dados.total_parcelas and dados.total_parcelas > 1) else None
    new_parcela = dados.parcela_atual or 1 if new_total else None
    desc_base = _SUFIXO_PARCELA.sub('', dados.descricao).strip()
    new_descricao = f"{desc_base} ({new_parcela}/{new_total})" if new_total else dados.descricao

    # Cancela parcelas futuras do grupo antigo quando: saiu do parcelado OU mudou configuração
    if old_grupo and (not new_total or old_parcela != new_parcela):
        _cancelar_futuras(db, old_grupo, old_parcela, current_user.id)

    item.descricao = new_descricao
    item.valor = dados.valor
    item.data_compra = dados.data_compra
    item.categoria_id = dados.categoria_id
    item.parcela_atual = new_parcela
    item.total_parcelas = new_total
    item.grupo_parcela_id = old_grupo if new_total else None
    db.flush()
    fatura.valor_total = _recalcular_total(fatura.id, db)

    # Recria parcelas futuras se parcelado (novo ou reconfigurado)
    if new_total and new_parcela < new_total:
        grupo_id = old_grupo or item.id
        item.grupo_parcela_id = grupo_id
        db.flush()
        _criar_futuras(db, fatura, desc_base, dados.valor, dados.data_compra,
                       dados.categoria_id, new_parcela, new_total, grupo_id, current_user.id)

    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_item(
    item_id: int,
    cancelar_futuras: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = db.query(models.ItemFatura).filter(
        models.ItemFatura.id == item_id,
        models.ItemFatura.user_id == current_user.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    fatura = db.query(models.FaturaCartao).filter(models.FaturaCartao.id == item.fatura_id).first()
    if fatura.status == "fechada":
        raise HTTPException(status_code=400, detail="Fatura fechada — reabra para remover itens")

    grupo_id = item.grupo_parcela_id
    parcela_atual = item.parcela_atual or 0
    fatura_id = item.fatura_id

    db.delete(item)
    db.flush()
    fatura.valor_total = _recalcular_total(fatura_id, db)

    if cancelar_futuras and grupo_id:
        _cancelar_futuras(db, grupo_id, parcela_atual, current_user.id)

    db.commit()
