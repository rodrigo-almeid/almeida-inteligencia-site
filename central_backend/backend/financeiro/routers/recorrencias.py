from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import extract
import calendar
from datetime import date

from backend.core import models
from backend.core.database import get_db
from backend.core.security import get_current_user, require_perfil

router = APIRouter(prefix="/recorrencias", tags=["Motor de Recorrência"], dependencies=[Depends(require_perfil("dashboard"))])

def somar_meses(data_original: date, meses_a_somar: int = 1) -> date:
    mes = data_original.month - 1 + meses_a_somar
    ano = data_original.year + mes // 12
    mes = mes % 12 + 1
    dia = min(data_original.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)

@router.post("/processar/")
def processar_recorrencias(mes: int, ano: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # 1. Filtra APENAS as contas do utilizador logado que são vitalícias/parceladas e não processadas
    contas_recorrentes = db.query(models.Conta).filter(
        extract('month', models.Conta.vencimento) == mes,
        extract('year', models.Conta.vencimento) == ano,
        models.Conta.tipo_recorrencia.in_(["Vitalícia", "vitalícia", "Parcelada", "parcelada"]),
        models.Conta.mes_seguinte_processado == 0,
        models.Conta.user_id == current_user.id
    ).all()

    novas_contas = []

    # 2. Clona as contas para o mês seguinte
    for conta in contas_recorrentes:
        # Se for parcelada, só continua se ainda houver parcelas
        if conta.tipo_recorrencia.lower() == "parcelada" and conta.parcela_atual >= conta.total_parcelas:
            continue

        novo_vencimento = somar_meses(conta.vencimento, 1)

        nova_conta = models.Conta(
            descricao=conta.descricao,
            vencimento=novo_vencimento,
            valor=conta.valor,
            natureza=conta.natureza,
            status="A Pagar",  # Volta ao status inicial para o próximo mês
            tipo_recorrencia=conta.tipo_recorrencia,
            parcela_atual=(conta.parcela_atual + 1) if conta.parcela_atual else 1,
            total_parcelas=conta.total_parcelas,
            mes_seguinte_processado=0,
            categoria_id=conta.categoria_id, # Copia a categoria
            user_id=current_user.id          # Amarra ao utilizador logado
        )
        db.add(nova_conta)
        novas_contas.append(nova_conta)

        # Marca a conta original do mês passado como processada
        conta.mes_seguinte_processado = 1

    db.commit()
    return {"mensagem": f"{len(novas_contas)} recorrências geradas com sucesso para o utilizador."}