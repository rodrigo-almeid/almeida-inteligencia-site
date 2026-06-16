import os
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.models import User
from backend.core.security import verify_password, create_token, get_current_user, hash_password

router = APIRouter(prefix="/auth", tags=["Auth"])

PORTAL_SECRET_KEY = os.getenv("PORTAL_SECRET_KEY", "")
PORTAL_ALGORITHM = "HS256"


class SSORequest(BaseModel):
    portal_token: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str
    nome: str
    email: str


class MeOut(BaseModel):
    id: int
    nome: str
    email: str


@router.post("/login", response_model=LoginOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username, User.ativo == True).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")
    token = create_token(user.id)
    return {"access_token": token, "token_type": "bearer", "nome": user.nome, "email": user.email}


@router.get("/me", response_model=MeOut)
def me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "nome": current_user.nome, "email": current_user.email}


@router.post("/sso")
def sso(body: SSORequest, db: Session = Depends(get_db)):
    if not PORTAL_SECRET_KEY:
        raise HTTPException(status_code=500, detail="SSO não configurado")
    try:
        payload = jwt.decode(body.portal_token, PORTAL_SECRET_KEY, algorithms=[PORTAL_ALGORITHM])
        email: str = payload.get("email")
        nome: str = payload.get("email", "").split("@")[0]
        if not email:
            raise HTTPException(status_code=401, detail="Token inválido")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token do portal inválido")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(nome=nome, email=email, password_hash=hash_password(os.urandom(16).hex()))
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_token(user.id)
    return {"access_token": token, "token_type": "bearer", "nome": user.nome, "email": user.email}
