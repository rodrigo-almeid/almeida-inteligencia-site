import calendar
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user, require_perfil

router = APIRouter(
    prefix="/faturas",
    tags=["Faturas Cartão"],
    dependencies=[Depends(require_perfil("automacao_financeira"))],
)


@router.get("/", response_model=schemas.FaturaCartaoResponse)
def buscar_ou_criar_fatura(
    cartao_id: int,
    mes: int,
    ano: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cartao = db.query(models.Cartao).filter(
        models.Cartao.id == cartao_id,
        models.Cartao.user_id == current_user.id,
    ).first()
    if not cartao:
        raise HTTPException(status_code=404, detail="Cartão não encontrado")

    mes_ref = f"{ano}-{mes:02d}"
    fatura = db.query(models.FaturaCartao).filter(
        models.FaturaCartao.cartao_id == cartao_id,
        models.FaturaCartao.mes_referencia == mes_ref,
        models.FaturaCartao.user_id == current_user.id,
    ).first()

    if not fatura:
        fatura = models.FaturaCartao(
            cartao_id=cartao_id,
            mes_referencia=mes_ref,
            valor_total=0.0,
            status="aberta",
            user_id=current_user.id,
        )
        db.add(fatura)
        db.commit()
        db.refresh(fatura)

    return fatura


@router.post("/{fatura_id}/fechar", response_model=schemas.FaturaCartaoResponse)
def fechar_fatura(
    fatura_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    fatura = db.query(models.FaturaCartao).filter(
        models.FaturaCartao.id == fatura_id,
        models.FaturaCartao.user_id == current_user.id,
    ).first()
    if not fatura:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    if fatura.status == "fechada":
        raise HTTPException(status_code=400, detail="Fatura já está fechada")

    cartao = db.query(models.Cartao).filter(models.Cartao.id == fatura.cartao_id).first()

    total = db.query(func.sum(models.ItemFatura.valor)).filter(
        models.ItemFatura.fatura_id == fatura.id
    ).scalar() or 0.0

    total_pago = db.query(func.sum(models.PagamentoFatura.valor)).filter(
        models.PagamentoFatura.fatura_id == fatura.id
    ).scalar() or 0.0

    saldo_restante = max(total - total_pago, 0.0)

    ano_ref = int(fatura.mes_referencia[:4])
    mes_ref = int(fatura.mes_referencia[5:7])
    mes_venc = mes_ref + 1
    ano_venc = ano_ref
    if mes_venc > 12:
        mes_venc = 1
        ano_venc += 1
    dia_venc = min(cartao.dia_vencimento, calendar.monthrange(ano_venc, mes_venc)[1])
    vencimento = date(ano_venc, mes_venc, dia_venc)

    nova_conta = models.Conta(
        descricao=f"Fatura {cartao.nome} {fatura.mes_referencia}",
        vencimento=vencimento,
        competencia=fatura.mes_referencia,
        valor=saldo_restante,
        natureza="despesa",
        status="pendente",
        tipo_recorrencia="unica",
        user_id=current_user.id,
    )
    db.add(nova_conta)
    db.flush()

    fatura.conta_id = nova_conta.id
    fatura.valor_total = total
    fatura.status = "fechada"
    db.commit()
    db.refresh(fatura)
    return fatura


@router.post("/{fatura_id}/reabrir", response_model=schemas.FaturaCartaoResponse)
def reabrir_fatura(
    fatura_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    fatura = db.query(models.FaturaCartao).filter(
        models.FaturaCartao.id == fatura_id,
        models.FaturaCartao.user_id == current_user.id,
    ).first()
    if not fatura:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    if fatura.status == "aberta":
        raise HTTPException(status_code=400, detail="Fatura já está aberta")

    # Remove a Conta gerada automaticamente se ainda estiver pendente
    if fatura.conta_id:
        conta = db.query(models.Conta).filter(models.Conta.id == fatura.conta_id).first()
        if conta and conta.status == "pendente":
            db.delete(conta)

    fatura.status = "aberta"
    fatura.conta_id = None
    db.commit()
    db.refresh(fatura)
    return fatura
