from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.models import User
from backend.core.security import verify_password, create_token, get_current_user, hash_password

router = APIRouter(prefix="/auth", tags=["Auth"])


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
