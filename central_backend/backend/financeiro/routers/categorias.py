from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from fastapi import Depends
from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user, require_perfil

router = APIRouter(prefix="/categorias", tags=["Categorias"], dependencies=[Depends(require_perfil("dashboard"))])


@router.post("/", response_model=schemas.CategoriaResponse, status_code=status.HTTP_201_CREATED)
def criar_categoria(categoria: schemas.CategoriaCreate, db: Session = Depends(get_db),
                    current_user: models.User = Depends(get_current_user)):
    nome_formatado = categoria.nome.strip().capitalize()

    # Verifica duplicado APENAS para o usuário logado
    db_categoria = db.query(models.Categoria).filter(
        models.Categoria.nome == nome_formatado,
        models.Categoria.user_id == current_user.id
    ).first()

    if db_categoria:
        raise HTTPException(status_code=400, detail="Esta categoria já existe.")

    # Amarra a categoria ao usuário
    nova_categoria = models.Categoria(nome=nome_formatado, user_id=current_user.id)
    db.add(nova_categoria)
    db.commit()
    db.refresh(nova_categoria)
    return nova_categoria


@router.get("/", response_model=List[schemas.CategoriaResponse])
def listar_categorias(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Retorna apenas as categorias do usuário logado
    return db.query(models.Categoria).filter(models.Categoria.user_id == current_user.id).all()