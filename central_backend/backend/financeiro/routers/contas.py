from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import extract, or_, and_
from sqlalchemy.orm import Session
from typing import List, Optional
import calendar
from datetime import date

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user, require_perfil

router = APIRouter(prefix="/contas", tags=["Contas"], dependencies=[Depends(require_perfil("dashboard"))])


def somar_meses(data_original: date, meses_a_somar: int) -> date:
    if meses_a_somar == 0:
        return data_original
    mes = data_original.month - 1 + meses_a_somar
    ano = data_original.year + mes // 12
    mes = mes % 12 + 1
    dia = min(data_original.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


@router.post("/", response_model=schemas.ContaResponse, status_code=status.HTTP_201_CREATED)
def criar_conta(conta: schemas.ContaCreate, db: Session = Depends(get_db),
                current_user: models.User = Depends(get_current_user)):
    dados_conta = conta.model_dump()
    dados_conta["user_id"] = current_user.id

    tipo_rec = conta.tipo_recorrencia.lower() if conta.tipo_recorrencia else "unica"

    # Lógica de parcelamento
    if tipo_rec == "parcelada" and conta.total_parcelas and conta.total_parcelas > 1:
        primeira_conta = None
        for i in range(conta.total_parcelas):
            dados_parcela = dados_conta.copy()
            dados_parcela["parcela_atual"] = i + 1
            dados_parcela["vencimento"] = somar_meses(conta.vencimento, i)
            if conta.competencia:
                comp_base = somar_meses(date(int(conta.competencia[:4]), int(conta.competencia[5:7]), 1), i)
                dados_parcela["competencia"] = f"{comp_base.year}-{comp_base.month:02d}"

            nova_parcela = models.Conta(**dados_parcela)
            db.add(nova_parcela)
            if i == 0:
                primeira_conta = nova_parcela

        db.commit()
        db.refresh(primeira_conta)
        return primeira_conta
    else:
        nova_conta = models.Conta(**dados_conta)
        db.add(nova_conta)
        db.commit()
        db.refresh(nova_conta)
        return nova_conta


@router.get("/", response_model=list[schemas.ContaResponse])
async def listar_contas(
        mes: Optional[int] = None,
        ano: Optional[int] = None,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(get_current_user)
):
    # 1. Começa por buscar apenas as contas do utilizador logado (Segurança)
    query = db.query(models.Conta).filter(models.Conta.user_id == current_user.id)

    # 2. Filtra por competência (se preenchida) ou vencimento como fallback
    if mes and ano:
        competencia_str = f"{ano}-{mes:02d}"
        query = query.filter(
            or_(
                # Tem competência definida e bate com o mês/ano solicitado
                and_(
                    models.Conta.competencia != None,
                    models.Conta.competencia == competencia_str
                ),
                # Sem competência: usa o mês/ano do vencimento
                and_(
                    models.Conta.competencia == None,
                    extract('year', models.Conta.vencimento) == ano,
                    extract('month', models.Conta.vencimento) == mes
                )
            )
        )

    # 3. Devolve apenas as contas filtradas
    return query.all()


@router.put("/{conta_id}", response_model=schemas.ContaResponse)
def atualizar_conta(conta_id: int, conta_atualizada: schemas.ContaCreate, db: Session = Depends(get_db),
                    current_user: models.User = Depends(get_current_user)):
    conta = db.query(models.Conta).filter(
        models.Conta.id == conta_id,
        models.Conta.user_id == current_user.id
    ).first()

    if not conta:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    for key, value in conta_atualizada.model_dump().items():
        setattr(conta, key, value)

    db.commit()
    db.refresh(conta)
    return conta


@router.delete("/{conta_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_conta(conta_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    conta = db.query(models.Conta).filter(
        models.Conta.id == conta_id,
        models.Conta.user_id == current_user.id
    ).first()

    if not conta:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    db.delete(conta)
    db.commit()
    return {"mensagem": "Conta eliminada com sucesso"}