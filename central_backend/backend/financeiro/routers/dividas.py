from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user, require_perfil

router = APIRouter(prefix="/dividas", tags=["Dívidas de Terceiros"], dependencies=[Depends(require_perfil("automacao_financeira"))])


@router.post("/", response_model=schemas.DividaResponse, status_code=status.HTTP_201_CREATED)
def criar_divida(divida: schemas.DividaCreate, db: Session = Depends(get_db),
                 current_user: models.User = Depends(get_current_user)):
    # Converte o schema para dicionário e injeta o ID do usuário
    dados_divida = divida.model_dump()
    dados_divida["user_id"] = current_user.id

    nova_divida = models.DividaTerceiro(**dados_divida)
    db.add(nova_divida)
    db.commit()
    db.refresh(nova_divida)
    return nova_divida


@router.get("/", response_model=List[schemas.DividaResponse])
def listar_dividas(skip: int = 0, limit: int = 100, db: Session = Depends(get_db),
                   current_user: models.User = Depends(get_current_user)):
    # Lista apenas as dívidas do usuário logado
    return db.query(models.DividaTerceiro).filter(models.DividaTerceiro.user_id == current_user.id).offset(skip).limit(
        limit).all()


@router.put("/{divida_id}", response_model=schemas.DividaResponse)
def atualizar_divida(divida_id: int, divida_atualizada: schemas.DividaCreate, db: Session = Depends(get_db),
                     current_user: models.User = Depends(get_current_user)):
    # Garante que ele só pode atualizar se a dívida for dele
    divida = db.query(models.DividaTerceiro).filter(
        models.DividaTerceiro.id == divida_id,
        models.DividaTerceiro.user_id == current_user.id
    ).first()

    if not divida:
        raise HTTPException(status_code=404, detail="Dívida não encontrada")

    for key, value in divida_atualizada.model_dump().items():
        setattr(divida, key, value)

    db.commit()
    db.refresh(divida)
    return divida


@router.delete("/{divida_id}")
async def excluir_divida(divida_id: int, db: Session = Depends(get_db),
                         current_user: models.User = Depends(get_current_user)):
    db_divida = db.query(models.DividaTerceiro).filter(
        models.DividaTerceiro.id == divida_id,
        models.DividaTerceiro.user_id == current_user.id
    ).first()

    # Se não encontrar, dá erro 404
    if db_divida is None:
        raise HTTPException(status_code=404, detail="Dívida não encontrada")

    # Se encontrar, apaga e grava no banco
    db.delete(db_divida)
    db.commit()

    return {"message": "Dívida apagada com sucesso"}