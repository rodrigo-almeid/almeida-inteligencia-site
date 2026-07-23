import os
from typing import Optional
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import bcrypt  # <-- Usando a biblioteca nativa atualizada
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from backend.core.database import get_db
from backend.core import models

load_dotenv()

# Tenta ler a chave do .env (note que tirei o "plano B")
SECRET_KEY = os.getenv("JWT_SECRET_KEY")

# Trava de segurança: Se a chave não existir, o sistema não arranca
if not SECRET_KEY:  # pragma: no cover
    raise ValueError("ERRO: A variável JWT_SECRET_KEY não foi encontrada no ficheiro .env!")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


# ==========================================
# FUNÇÕES DE CRIPTOGRAFIA E TOKEN (NATIVO)
# ==========================================
def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), password_hash.encode('utf-8'))


# CORREÇÃO: Usando Optional[timedelta] em vez de timedelta | None
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ==========================================
# DEPENDÊNCIA: VERIFICA O UTILIZADOR LOGADO
# ==========================================
def require_perfil(perfil_nome: str):
    """Verifica se o usuário autenticado possui o perfil exigido pela rota."""
    def build_checker(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
        user = get_current_user(token, db)
        nomes = [p.nome for p in user.perfis]
        if perfil_nome not in nomes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso negado. Perfil '{perfil_nome}' necessário.",
            )
        return user
    return build_checker


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception
    return user