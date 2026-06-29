from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import os
from cryptography.fernet import Fernet

from backend.core import models, schemas
from backend.core.database import get_db
from backend.core.security import get_current_user, require_perfil
import os
from cryptography.fernet import Fernet
CHAVE_MESTRA = os.getenv("FERNET_SECRET_KEY")
fernet = Fernet(CHAVE_MESTRA)
router = APIRouter(
    prefix="/me/senhas",
    tags=["Perfis e Propriedades"],
    dependencies=[Depends(require_perfil("gerenciador_credenciais"))],
)


# ===================================================
# 1. GERENCIAMENTO DE PERFIS (PESSOAS)
# ===================================================

@router.get("/perfil/", response_model=List[schemas.PessoaResponse])
def listar_perfis(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.Pessoa).filter(
        models.Pessoa.user_id == current_user.id
    ).order_by(models.Pessoa.id.asc()).all()


@router.post("/perfil/", response_model=schemas.PessoaResponse)
def criar_perfil(perfil: schemas.PessoaCreate, db: Session = Depends(get_db),
                 current_user: models.User = Depends(get_current_user)):
    total_perfis = db.query(models.Pessoa).filter(models.Pessoa.user_id == current_user.id).count()

    novo_perfil = models.Pessoa(
        nome=perfil.nome,
        user_id=current_user.id,
        principal=True if total_perfis == 0 else perfil.principal
    )
    db.add(novo_perfil)
    db.commit()
    db.refresh(novo_perfil)
    return novo_perfil


# ===================================================
# 2. GERENCIAMENTO DE CREDENCIAIS (SENHAS)
# ===================================================

# CORREÇÃO DO 404: Agora a rota bate exatamente onde o Front-end está chamando!
@router.get("/{pessoa_id}")
def listar_senhas(pessoa_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Verificar se o perfil pertence ao usuário logado
    perfil = db.query(models.Pessoa).filter(
        models.Pessoa.id == pessoa_id,
        models.Pessoa.user_id == current_user.id
    ).first()
    if not perfil:
        raise HTTPException(status_code=403, detail="Acesso negado.")
    credenciais = db.query(models.Senha).filter(models.Senha.pessoa_id == pessoa_id).all()

    # Vamos destrancar as senhas uma a uma antes de enviar
    for cred in credenciais:
        try:
            # Pega na senha trancada e destranca
            cred.senha_criptografada = fernet.decrypt(cred.senha_criptografada.encode()).decode()
        except Exception:
            # Se der erro (ex: senhas antigas de teste que não estavam encriptadas)
            cred.senha_criptografada = "Erro: Senha num formato antigo ou inválido"

    return credenciais

@router.post("/")
def cadastrar_senha(payload: schemas.SenhaCreate, db: Session = Depends(get_db),
                    current_user: models.User = Depends(get_current_user)):
    # 1. Trancar a senha com a chave-mestra
    senha_trancada = fernet.encrypt(payload.senha.encode()).decode()

    # 2. Guardar a versão encriptada no banco de dados
    nova_credencial = models.Senha(
        sistema=payload.sistema,
        usuario_sistema=payload.usuario_sistema,
        senha_criptografada=senha_trancada,  # Guardamos APENAS a versão trancada
        pessoa_id=payload.pessoa_id
    )

    db.add(nova_credencial)
    db.commit()
    return {"mensagem": "Credencial guardada em segurança."}
# ===================================================
# 3. PROPRIEDADES DINÂMICAS (DADOS PESSOAIS)
# ===================================================

@router.get("/propriedades/{pessoa_id}", response_model=List[schemas.DadoDinamicoResponse])
def listar_propriedades_do_perfil(pessoa_id: int, db: Session = Depends(get_db),
                                  current_user: models.User = Depends(get_current_user)):
    perfil = db.query(models.Pessoa).filter(
        models.Pessoa.id == pessoa_id,
        models.Pessoa.user_id == current_user.id
    ).first()

    if not perfil:
        raise HTTPException(status_code=403, detail="Perfil inválido.")

    return db.query(models.DadoPessoal).filter(models.DadoPessoal.pessoa_id == pessoa_id).all()


@router.post("/dados/", response_model=schemas.DadoDinamicoResponse)
def adicionar_propriedade_ao_perfil(dado: schemas.DadoDinamicoCreate, db: Session = Depends(get_db),
                                    current_user: models.User = Depends(get_current_user)):
    perfil = db.query(models.Pessoa).filter(
        models.Pessoa.id == dado.pessoa_id,
        models.Pessoa.user_id == current_user.id
    ).first()

    if not perfil:
        raise HTTPException(status_code=403, detail="Perfil inválido.")

    nova_propriedade = models.DadoPessoal(
        chave=dado.chave,
        valor=dado.valor,
        pessoa_id=dado.pessoa_id
    )
    db.add(nova_propriedade)
    db.commit()
    db.refresh(nova_propriedade)
    return nova_propriedade


@router.delete("/dados/{dado_id}")
def remover_propriedade(dado_id: int, db: Session = Depends(get_db),
                        current_user: models.User = Depends(get_current_user)):
    propriedade = db.query(models.DadoPessoal).filter(models.DadoPessoal.id == dado_id).first()
    if not propriedade:
        raise HTTPException(status_code=404, detail="Propriedade não encontrada.")

    # Verifica se a propriedade pertence a um perfil do usuário logado
    perfil = db.query(models.Pessoa).filter(
        models.Pessoa.id == propriedade.pessoa_id,
        models.Pessoa.user_id == current_user.id
    ).first()

    if not perfil:
        raise HTTPException(status_code=403, detail="Acesso negado.")

    db.delete(propriedade)
    db.commit()
    return {"mensagem": "Propriedade removida com sucesso."}


# ===================================================
# APAGAR CREDENCIAL (SENHA)
# ===================================================
@router.delete("/credencial/{senha_id}")
def remover_credencial(senha_id: int, db: Session = Depends(get_db),
                       current_user: models.User = Depends(get_current_user)):
    # Busca a senha no banco de dados
    credencial = db.query(models.Senha).filter(models.Senha.id == senha_id).first()

    if not credencial:
        raise HTTPException(status_code=404, detail="Credencial não encontrada.")

    # Proteção: Garante que a pessoa dona desta senha pertence ao usuário logado
    perfil = db.query(models.Pessoa).filter(
        models.Pessoa.id == credencial.pessoa_id,
        models.Pessoa.user_id == current_user.id
    ).first()

    if not perfil:
        raise HTTPException(status_code=403, detail="Você não tem permissão para apagar esta senha.")

    # Apaga do banco de dados
    db.delete(credencial)
    db.commit()

    return {"mensagem": "Credencial removida com sucesso"}