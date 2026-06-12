from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List
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


def create_token(user_id: int, email: str, perfil_slug: str, menus: list) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "perfil": perfil_slug,
        "menus": menus,
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
    perfil_id: Optional[int] = None
    ativo: bool = True

class UserUpdate(BaseModel):
    nome: Optional[str] = None
    email: Optional[str] = None
    senha: Optional[str] = None
    perfil_id: Optional[int] = None
    ativo: Optional[bool] = None

class PerfilCreate(BaseModel):
    nome: str
    descricao: Optional[str] = ""
    menus: List[str] = []

class PerfilUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    menus: Optional[List[str]] = None


# ── HELPERS ──
def get_user_menus(conn, perfil_id) -> list:
    if not perfil_id:
        return []
    cur = conn.cursor()
    cur.execute("SELECT menu_slug FROM perfil_menus WHERE perfil_id = %s", (perfil_id,))
    return [r["menu_slug"] for r in cur.fetchall()]

def get_perfil_slug(conn, perfil_id) -> str:
    if not perfil_id:
        return "cliente"
    cur = conn.cursor()
    cur.execute("SELECT slug FROM perfis WHERE id = %s", (perfil_id,))
    row = cur.fetchone()
    return row["slug"] if row else "cliente"


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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro de banco: {str(e)}")

    if not user:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    if not user["ativo"]:
        raise HTTPException(status_code=403, detail="Usuário desativado")
    if not bcrypt.checkpw(body.senha.encode(), user["senha_hash"].encode()):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    menus = get_user_menus(conn, user["perfil_id"])
    perfil_slug = get_perfil_slug(conn, user["perfil_id"])
    conn.close()

    token = create_token(user["id"], user["email"], perfil_slug, menus)
    return {
        "token": token,
        "perfil": perfil_slug,
        "nome": user["nome"],
        "email": user["email"],
        "menus": menus
    }


@app.get("/api/me")
def me(token=Depends(verify_token)):
    return token


# ── USUÁRIOS ──

@app.get("/api/usuarios")
def listar_usuarios(token=Depends(require_admin)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.id, u.nome, u.email, u.ativo, u.criado_em,
               u.perfil_id, p.nome as perfil_nome, p.slug as perfil_slug
        FROM usuarios u
        LEFT JOIN perfis p ON p.id = u.perfil_id
        ORDER BY u.id
    """)
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
            "INSERT INTO usuarios (nome, email, senha_hash, perfil_id, ativo) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (body.nome, body.email, senha_hash, body.perfil_id, body.ativo)
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
    if body.nome is not None: updates["nome"] = body.nome
    if body.email is not None: updates["email"] = body.email
    if body.perfil_id is not None: updates["perfil_id"] = body.perfil_id
    if body.ativo is not None: updates["ativo"] = body.ativo
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


# ── PERFIS ──

@app.get("/api/perfis")
def listar_perfis(token=Depends(require_admin)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM perfis ORDER BY id")
    perfis = cur.fetchall()
    result = []
    for p in perfis:
        cur.execute("SELECT menu_slug FROM perfil_menus WHERE perfil_id = %s", (p["id"],))
        menus = [r["menu_slug"] for r in cur.fetchall()]
        cur.execute("SELECT COUNT(*) as total FROM usuarios WHERE perfil_id = %s", (p["id"],))
        total_users = cur.fetchone()["total"]
        result.append({**dict(p), "menus": menus, "total_usuarios": total_users})
    conn.close()
    return result


@app.post("/api/perfis", status_code=201)
def criar_perfil(body: PerfilCreate, token=Depends(require_admin)):
    slug = body.nome.lower().strip().replace(" ", "_")
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO perfis (nome, slug, descricao) VALUES (%s,%s,%s) RETURNING id",
            (body.nome, slug, body.descricao)
        )
        perfil_id = cur.fetchone()["id"]
        for menu in body.menus:
            cur.execute("INSERT INTO perfil_menus (perfil_id, menu_slug) VALUES (%s,%s)", (perfil_id, menu))
        conn.commit()
        conn.close()
        return {"id": perfil_id, "mensagem": "Perfil criado"}
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="Perfil com esse nome já existe")


@app.put("/api/perfis/{perfil_id}")
def atualizar_perfil(perfil_id: int, body: PerfilUpdate, token=Depends(require_admin)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM perfis WHERE id = %s", (perfil_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    if body.nome is not None:
        slug = body.nome.lower().strip().replace(" ", "_")
        cur.execute("UPDATE perfis SET nome=%s, slug=%s WHERE id=%s", (body.nome, slug, perfil_id))
    if body.descricao is not None:
        cur.execute("UPDATE perfis SET descricao=%s WHERE id=%s", (body.descricao, perfil_id))
    if body.menus is not None:
        cur.execute("DELETE FROM perfil_menus WHERE perfil_id=%s", (perfil_id,))
        for menu in body.menus:
            cur.execute("INSERT INTO perfil_menus (perfil_id, menu_slug) VALUES (%s,%s)", (perfil_id, menu))

    conn.commit()
    conn.close()
    return {"mensagem": "Perfil atualizado"}


@app.delete("/api/perfis/{perfil_id}")
def deletar_perfil(perfil_id: int, token=Depends(require_admin)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as total FROM usuarios WHERE perfil_id = %s", (perfil_id,))
    if cur.fetchone()["total"] > 0:
        conn.close()
        raise HTTPException(status_code=400, detail="Remova os usuários deste perfil antes de deletá-lo")
    cur.execute("DELETE FROM perfil_menus WHERE perfil_id=%s", (perfil_id,))
    cur.execute("DELETE FROM perfis WHERE id=%s RETURNING id", (perfil_id,))
    deleted = cur.fetchone()
    conn.commit()
    conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")
    return {"mensagem": "Perfil removido"}
