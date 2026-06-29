from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from backend.core.database import get_db
from backend.core import models, schemas
from backend.core.security import get_current_user, require_perfil

router = APIRouter(
    prefix="/pessoas",
    tags=["Pessoas"],
    dependencies=[Depends(require_perfil("gerenciador_credenciais"))],
)


# 1. CADASTRAR NOVO PERFIL CONTEXTUAL
@router.post("/", response_model=schemas.PessoaResponse, status_code=status.HTTP_201_CREATED)
def criar_pessoa(pessoa: schemas.PessoaCreate, db: Session = Depends(get_db),
                 current_user: models.User = Depends(get_current_user)):
    nome_existe = db.query(models.Pessoa).filter(
        models.Pessoa.user_id == current_user.id,
        models.Pessoa.nome.ilike(pessoa.nome)
    ).first()

    if nome_existe:
        raise HTTPException(status_code=400, detail="Você já possui um perfil cadastrado com este nome.")

    primeiro_perfil = db.query(models.Pessoa).filter(models.Pessoa.user_id == current_user.id).count() == 0

    nova_pessoa = models.Pessoa(
        nome=pessoa.nome,
        user_id=current_user.id,
        principal=primeiro_perfil
    )
    db.add(nova_pessoa)
    db.commit()
    db.refresh(nova_pessoa)
    return nova_pessoa


# 2. LISTAR PERFIS CORPORATIVOS DO USUÁRIO LOGADO
@router.get("/", response_model=List[schemas.PessoaResponse])
def listar_pessoas(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.Pessoa).filter(models.Pessoa.user_id == current_user.id).order_by(models.Pessoa.nome).all()


# 3. DEFINIR UM PERFIL COMO PADRÃO / PRINCIPAL
@router.post("/{pessoa_id}/principal", response_model=schemas.PessoaResponse)
def definir_principal(pessoa_id: int, db: Session = Depends(get_db),
                      current_user: models.User = Depends(get_current_user)):
    # CORRIGIDO: Removido o 'presidential_id' que causava erro de sintaxe
    pessoa = db.query(models.Pessoa).filter(
        models.Pessoa.id == pessoa_id,
        models.Pessoa.user_id == current_user.id
    ).first()

    if not pessoa:  # <-- Mude de 'pando' para 'pessoa'
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")

    db.query(models.Pessoa).filter(models.Pessoa.user_id == current_user.id).update({models.Pessoa.principal: False})

    pessoa.principal = True
    db.commit()
    db.refresh(pessoa)
    return pessoa