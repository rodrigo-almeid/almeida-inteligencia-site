import os
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from backend.core.database import get_db
from backend.core import models, schemas
from backend.core.security import get_password_hash, verify_password, create_access_token
from backend.core.rate_limit import limiter

router = APIRouter(prefix="/auth", tags=["Autenticação"])

PORTAL_SECRET_KEY = os.getenv("PORTAL_SECRET_KEY", "")
PORTAL_ALGORITHM = "HS256"


class SSORequest(BaseModel):
    portal_token: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def register(request: Request, user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    # 1. Verifica se o e-mail já existe
    db_user = db.query(models.User).filter(models.User.email == user_data.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")

    # 2. Cria o novo usuário com a coluna correta (hashed_password)
    hashed_password = get_password_hash(user_data.password)
    new_user = models.User(email=user_data.email, hashed_password=hashed_password)

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 3. AUTOMAÇÃO: Cria automaticamente o primeiro perfil (Pessoa) principal para o usuário
    perfil_padrao = models.Pessoa(
        nome="Meu Perfil",
        user_id=new_user.id,
        principal=True
    )
    db.add(perfil_padrao)
    db.commit()

    return {"message": "Usuário e perfil inicial criados com sucesso!"}


@router.post("/login")
@limiter.limit("10/minute")
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()

    if not user:
        raise HTTPException(status_code=400, detail="Credenciais inválidas")

    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Credenciais inválidas")

    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/sso")
def sso(body: SSORequest, db: Session = Depends(get_db)):
    if not PORTAL_SECRET_KEY:
        raise HTTPException(status_code=500, detail="SSO não configurado")
    try:
        payload = jwt.decode(body.portal_token, PORTAL_SECRET_KEY, algorithms=[PORTAL_ALGORITHM])
        email: str = payload.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Token inválido")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token do portal inválido")

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        user = models.User(email=email, hashed_password=get_password_hash(os.urandom(32).hex()))
        db.add(user)
        db.commit()
        db.refresh(user)
        perfil = models.Pessoa(nome="Meu Perfil", user_id=user.id, principal=True)
        db.add(perfil)
        db.commit()

    portal_perfil_slug = payload.get("perfil")
    portal_sistemas = payload.get("sistemas", [])

    if portal_perfil_slug == "admin":
        # O Portal manda 'sistemas' vazio pra admin (a tela dele já mostra tudo sem
        # depender dessa lista) — sincroniza com TODOS os perfis do central_backend
        # em vez disso, senão o bloco abaixo nunca roda (lista vazia é falsy) e um
        # admin do Portal não ganha nenhum acesso real nos módulos.
        user.perfis.clear()
        for perfil in db.query(models.Perfil).all():
            user.perfis.append(perfil)
        db.commit()
    elif portal_sistemas:
        slugs = [s["slug"] for s in portal_sistemas if isinstance(s, dict) and "slug" in s]
        user.perfis.clear()
        for slug in slugs:
            perfil = db.query(models.Perfil).filter(models.Perfil.nome == slug).first()
            if not perfil:
                perfil = models.Perfil(nome=slug)
                db.add(perfil)
                db.flush()
            user.perfis.append(perfil)
        db.commit()

    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer", "email": user.email}
