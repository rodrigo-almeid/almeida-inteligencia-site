from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import extract
from sqlalchemy.orm import Session
from typing import List, Optional
import statistics

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user, require_perfil

router = APIRouter(prefix="/abastecimentos", tags=["Abastecimentos"], dependencies=[Depends(require_perfil("abastecimento"))])


@router.post("/", response_model=schemas.AbastecimentoResponse, status_code=status.HTTP_201_CREATED)
def criar_abastecimento(
        abastecimento: schemas.AbastecimentoCreate,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(get_current_user)
):
    # 1. Busca o último abastecimento deste utilizador para pegar a KM Anterior
    ultimo = db.query(models.Abastecimento).filter(
        models.Abastecimento.user_id == current_user.id
    ).order_by(models.Abastecimento.km_atual.desc()).first()

    km_anterior = ultimo.km_atual if ultimo else None
    distancia = None
    media = None

    # 2. O Motor Matemático (Só calcula se o KM avançou e o tanque foi cheio)
    if km_anterior and abastecimento.km_atual > km_anterior:
        distancia = abastecimento.km_atual - km_anterior
        if abastecimento.tanque_cheio and abastecimento.litros > 0:
            media = distancia / abastecimento.litros

    # Transforma o payload em um dicionário para injeção
    dados_abastecimento = abastecimento.model_dump()

    # 3. Salva o Abastecimento no Banco
    novo_abastecimento = models.Abastecimento(
        **dados_abastecimento,
        km_anterior=km_anterior,
        distancia_percorrida=distancia,
        media_consumo=media,
        user_id=current_user.id
    )
    db.add(novo_abastecimento)

    # 4. Integração Cross-Módulo Mágica (Combustível -> Contas)
    formas_a_vista = ["pix", "débito", "debito", "dinheiro"]
    if abastecimento.forma_pagamento.lower() in formas_a_vista:

        # Garante que a Categoria "Combustível" exista para este usuário
        categoria = db.query(models.Categoria).filter(
            models.Categoria.nome.ilike("Combustível"),
            models.Categoria.user_id == current_user.id
        ).first()

        if not categoria:
            categoria = models.Categoria(nome="Combustível", user_id=current_user.id)
            db.add(categoria)
            db.commit()

        # Insere direto nas Contas como Pago
        nova_conta = models.Conta(
            descricao=f"Abastecimento - {abastecimento.tipo_combustivel}",
            vencimento=abastecimento.data,
            valor=abastecimento.valor_total,
            natureza="debito",
            status="pago",
            tipo_recorrencia="unica",
            parcela_atual=1,
            total_parcelas=1,
            user_id=current_user.id
        )
        db.add(nova_conta)

    db.commit()
    db.refresh(novo_abastecimento)
    return novo_abastecimento


@router.get("/")
def listar_abastecimentos(
        mes: Optional[int] = None,
        ano: Optional[int] = None,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(get_current_user)
):
    # 1. Inicia a query filtrando pelo utilizador
    query = db.query(models.Abastecimento).filter(models.Abastecimento.user_id == current_user.id)

    # 2. Filtro de data usando busca de texto (LIKE), pois a coluna é String
    if mes and ano:
        mes_formatado = str(mes).zfill(2)  # Transforma 6 em "06"
        prefixo_data = f"{ano}-{mes_formatado}"  # Fica "2026-06"
        query = query.filter(models.Abastecimento.data.like(f"{prefixo_data}%"))

    abastecimentos = query.order_by(models.Abastecimento.data.desc()).all()

    # 3. Busca o histórico INTEIRO de médias do usuário (ignorando o filtro de mês)
    historico = db.query(models.Abastecimento).filter(
        models.Abastecimento.user_id == current_user.id,
        models.Abastecimento.media_consumo.isnot(None)
    ).all()

    medias_gasolina = [a.media_consumo for a in historico if a.tipo_combustivel.lower() == "gasolina"]
    medias_etanol = [a.media_consumo for a in historico if a.tipo_combustivel.lower() == "etanol"]

    # Calcula a mediana exata
    mediana_gasolina = statistics.median(medias_gasolina) if medias_gasolina else 0.0
    mediana_etanol = statistics.median(medias_etanol) if medias_etanol else 0.0

    return {
        "abastecimentos": abastecimentos,
        "estatisticas": {
            "mediana_gasolina": round(mediana_gasolina, 2),
            "mediana_etanol": round(mediana_etanol, 2)
        }
    }


@router.delete("/{abastecimento_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_abastecimento(
        abastecimento_id: int,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(get_current_user)
):
    abastecimento = db.query(models.Abastecimento).filter(
        models.Abastecimento.id == abastecimento_id,
        models.Abastecimento.user_id == current_user.id
    ).first()

    if not abastecimento:
        raise HTTPException(status_code=404, detail="Abastecimento não encontrado")

    db.delete(abastecimento)
    db.commit()
    return {"mensagem": "Abastecimento eliminado com sucesso"}