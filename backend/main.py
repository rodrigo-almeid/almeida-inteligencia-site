from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
import psycopg2
import psycopg2.extras
import bcrypt
import jwt
import os
from datetime import datetime, timedelta

app = FastAPI(title="Almeida Inteligência Auth API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = os.getenv("SECRET_KEY", "almeida-secret-change-in-prod")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 8

DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "almeida")
DB_USER = os.getenv("DB_USER", "almeida")
DB_PASS = os.getenv("DB_PASS", "almeida123")

security = HTTPBearer()


def get_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
        cursor_factory=psycopg2.extras.RealDictCursor
    )


def create_token(user_id: int, email: str, perfil: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "perfil": perfil,
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")


def require_admin(token=Depends(verify_token)):
    if token.get("perfil") != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito ao administrador")
    return token


# ── SCHEMAS ──
class LoginRequest(BaseModel):
    email: str
    senha: str

class UserCreate(BaseModel):
    nome: str
    email: str
    senha: str
    perfil: str = "cliente"
    ativo: bool = True

class UserUpdate(BaseModel):
    nome: Optional[str] = None
    email: Optional[str] = None
    senha: Optional[str] = None
    perfil: Optional[str] = None
    ativo: Optional[bool] = None


# ── ROTAS ──

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/login")
def login(body: LoginRequest):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM usuarios WHERE email = %s", (body.email,))
        user = cur.fetchone()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro de banco: {str(e)}")

    if not user:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    if not user["ativo"]:
        raise HTTPException(status_code=403, detail="Usuário desativado")

    if not bcrypt.checkpw(body.senha.encode(), user["senha_hash"].encode()):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    token = create_token(user["id"], user["email"], user["perfil"])
    return {
        "token": token,
        "perfil": user["perfil"],
        "nome": user["nome"],
        "email": user["email"]
    }


@app.get("/api/me")
def me(token=Depends(verify_token)):
    return token


@app.get("/api/usuarios")
def listar_usuarios(token=Depends(require_admin)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, nome, email, perfil, ativo, criado_em FROM usuarios ORDER BY id")
    users = cur.fetchall()
    conn.close()
    return [dict(u) for u in users]


@app.post("/api/usuarios", status_code=201)
def criar_usuario(body: UserCreate, token=Depends(require_admin)):
    senha_hash = bcrypt.hashpw(body.senha.encode(), bcrypt.gensalt()).decode()
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO usuarios (nome, email, senha_hash, perfil, ativo) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (body.nome, body.email, senha_hash, body.perfil, body.ativo)
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
        conn.close()
        return {"id": new_id, "mensagem": "Usuário criado com sucesso"}
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="E-mail já cadastrado")


@app.put("/api/usuarios/{user_id}")
def atualizar_usuario(user_id: int, body: UserUpdate, token=Depends(require_admin)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM usuarios WHERE id = %s", (user_id,))
    user = cur.fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    updates = {}
    if body.nome is not None:
        updates["nome"] = body.nome
    if body.email is not None:
        updates["email"] = body.email
    if body.perfil is not None:
        updates["perfil"] = body.perfil
    if body.ativo is not None:
        updates["ativo"] = body.ativo
    if body.senha is not None:
        updates["senha_hash"] = bcrypt.hashpw(body.senha.encode(), bcrypt.gensalt()).decode()

    if updates:
        sets = ", ".join(f"{k} = %s" for k in updates)
        vals = list(updates.values()) + [user_id]
        cur.execute(f"UPDATE usuarios SET {sets} WHERE id = %s", vals)
        conn.commit()

    conn.close()
    return {"mensagem": "Usuário atualizado"}


@app.delete("/api/usuarios/{user_id}")
def deletar_usuario(user_id: int, token=Depends(require_admin)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM usuarios WHERE id = %s RETURNING id", (user_id,))
    deleted = cur.fetchone()
    conn.commit()
    conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return {"mensagem": "Usuário removido"}
