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

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8080").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("ERRO: A variável SECRET_KEY não foi configurada!")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 8

DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "almeida")
DB_USER = os.getenv("DB_USER", "almeida")
DB_PASS = os.getenv("DB_PASS", "")

security = HTTPBearer()


def get_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
        cursor_factory=psycopg2.extras.RealDictCursor
    )


def create_token(user_id: int, email: str, perfil_slug: str, sistemas: list) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "perfil": perfil_slug,
        "sistemas": sistemas,
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


def get_user_sistemas(conn, perfil_id) -> list:
    if not perfil_id:
        return []
    cur = conn.cursor()
    cur.execute("""
        SELECT s.id, s.nome, s.slug, s.descricao, s.url, s.icone
        FROM portal_perfil_sistemas ps
        JOIN sistemas s ON s.id = ps.sistema_id
        WHERE ps.perfil_id = %s AND s.ativo = TRUE
        ORDER BY s.nome
    """, (perfil_id,))
    return [dict(r) for r in cur.fetchall()]


def get_perfil_slug(conn, perfil_id) -> str:
    if not perfil_id:
        return "cliente"
    cur = conn.cursor()
    cur.execute("SELECT slug FROM portal_perfis WHERE id = %s", (perfil_id,))
    row = cur.fetchone()
    return row["slug"] if row else "cliente"


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
    sistemas: List[int] = []

class PerfilUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    sistemas: Optional[List[int]] = None

class SistemaCreate(BaseModel):
    nome: str
    slug: str
    descricao: Optional[str] = ""
    url: str
    icone: Optional[str] = "🖥️"
    ativo: bool = True

class SistemaUpdate(BaseModel):
    nome: Optional[str] = None
    slug: Optional[str] = None
    descricao: Optional[str] = None
    url: Optional[str] = None
    icone: Optional[str] = None
    ativo: Optional[bool] = None


# ── HEALTH ──
@app.get("/api/health")
def health():
    return {"status": "ok"}


# ── LOGIN ──
@app.post("/api/login")
def login(body: LoginRequest):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM usuarios WHERE email = %s", (body.email,))
        user = cur.fetchone()
    except Exception as e:
        print(f"[login] Erro de banco: {e}")
        raise HTTPException(status_code=500, detail="Erro interno do servidor")

    if not user:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    if not user["ativo"]:
        raise HTTPException(status_code=403, detail="Usuário desativado")
    if not bcrypt.checkpw(body.senha.encode(), user["senha_hash"].encode()):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    perfil_slug = get_perfil_slug(conn, user["perfil_id"])
    sistemas = [] if perfil_slug == "admin" else get_user_sistemas(conn, user["perfil_id"])
    conn.close()

    token = create_token(user["id"], user["email"], perfil_slug, sistemas)
    return {
        "token": token,
        "perfil": perfil_slug,
        "nome": user["nome"],
        "email": user["email"],
        "sistemas": sistemas
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
        FROM usuarios u LEFT JOIN portal_perfis p ON p.id = u.perfil_id ORDER BY u.id
    """)
    users = cur.fetchall()
    conn.close()
    return [dict(u) for u in users]


@app.post("/api/usuarios", status_code=201)
def criar_usuario(body: UserCreate, token=Depends(require_admin)):
    senha_hash = bcrypt.hashpw(body.senha.encode(), bcrypt.gensalt()).decode()
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO usuarios (nome, email, senha_hash, perfil_id, ativo) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (body.nome, body.email, senha_hash, body.perfil_id, body.ativo)
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
        return {"id": new_id, "mensagem": "Usuário criado"}
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="E-mail já cadastrado")
    finally:
        if conn:
            conn.close()


@app.put("/api/usuarios/{user_id}")
def atualizar_usuario(user_id: int, body: UserUpdate, token=Depends(require_admin)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM usuarios WHERE id = %s", (user_id,))
    if not cur.fetchone():
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
        cur.execute(f"UPDATE usuarios SET {sets} WHERE id = %s", list(updates.values()) + [user_id])
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
    cur.execute("SELECT * FROM portal_perfis ORDER BY id")
    perfis = cur.fetchall()
    result = []
    for p in perfis:
        cur.execute("""
            SELECT s.id, s.nome, s.slug, s.icone FROM portal_perfil_sistemas ps
            JOIN sistemas s ON s.id = ps.sistema_id WHERE ps.perfil_id = %s
        """, (p["id"],))
        sistemas = [dict(s) for s in cur.fetchall()]
        cur.execute("SELECT COUNT(*) as total FROM usuarios WHERE perfil_id = %s", (p["id"],))
        total = cur.fetchone()["total"]
        result.append({**dict(p), "sistemas": sistemas, "total_usuarios": total})
    conn.close()
    return result


@app.post("/api/perfis", status_code=201)
def criar_perfil(body: PerfilCreate, token=Depends(require_admin)):
    slug = body.nome.lower().strip().replace(" ", "_")
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("INSERT INTO portal_perfis (nome, slug, descricao) VALUES (%s,%s,%s) RETURNING id",
                    (body.nome, slug, body.descricao))
        perfil_id = cur.fetchone()["id"]
        for sid in body.sistemas:
            cur.execute("INSERT INTO portal_perfil_sistemas (perfil_id, sistema_id) VALUES (%s,%s)", (perfil_id, sid))
        conn.commit()
        return {"id": perfil_id, "mensagem": "Perfil criado"}
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="Perfil com esse nome já existe")
    finally:
        if conn:
            conn.close()


@app.put("/api/perfis/{perfil_id}")
def atualizar_perfil(perfil_id: int, body: PerfilUpdate, token=Depends(require_admin)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM portal_perfis WHERE id = %s", (perfil_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    if body.nome is not None:
        slug = body.nome.lower().strip().replace(" ", "_")
        cur.execute("UPDATE portal_perfis SET nome=%s, slug=%s WHERE id=%s", (body.nome, slug, perfil_id))
    if body.descricao is not None:
        cur.execute("UPDATE portal_perfis SET descricao=%s WHERE id=%s", (body.descricao, perfil_id))
    if body.sistemas is not None:
        cur.execute("DELETE FROM portal_perfil_sistemas WHERE perfil_id=%s", (perfil_id,))
        for sid in body.sistemas:
            cur.execute("INSERT INTO portal_perfil_sistemas (perfil_id, sistema_id) VALUES (%s,%s)", (perfil_id, sid))

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
    cur.execute("DELETE FROM portal_perfil_sistemas WHERE perfil_id=%s", (perfil_id,))
    cur.execute("DELETE FROM portal_perfis WHERE id=%s RETURNING id", (perfil_id,))
    deleted = cur.fetchone()
    conn.commit()
    conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")
    return {"mensagem": "Perfil removido"}


# ── SISTEMAS ──
@app.get("/api/sistemas")
def listar_sistemas(token=Depends(require_admin)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sistemas ORDER BY nome")
    sistemas = cur.fetchall()
    conn.close()
    return [dict(s) for s in sistemas]


@app.post("/api/sistemas", status_code=201)
def criar_sistema(body: SistemaCreate, token=Depends(require_admin)):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO sistemas (nome, slug, descricao, url, icone, ativo) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (body.nome, body.slug, body.descricao, body.url, body.icone, body.ativo)
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
        conn.close()
        return {"id": new_id, "mensagem": "Sistema criado"}
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="Slug já existe")


@app.put("/api/sistemas/{sistema_id}")
def atualizar_sistema(sistema_id: int, body: SistemaUpdate, token=Depends(require_admin)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sistemas WHERE id = %s", (sistema_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Sistema não encontrado")

    updates = {}
    if body.nome is not None: updates["nome"] = body.nome
    if body.slug is not None: updates["slug"] = body.slug
    if body.descricao is not None: updates["descricao"] = body.descricao
    if body.url is not None: updates["url"] = body.url
    if body.icone is not None: updates["icone"] = body.icone
    if body.ativo is not None: updates["ativo"] = body.ativo

    if updates:
        sets = ", ".join(f"{k} = %s" for k in updates)
        cur.execute(f"UPDATE sistemas SET {sets} WHERE id = %s", list(updates.values()) + [sistema_id])
        conn.commit()
    conn.close()
    return {"mensagem": "Sistema atualizado"}


@app.delete("/api/sistemas/{sistema_id}")
def deletar_sistema(sistema_id: int, token=Depends(require_admin)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM portal_perfil_sistemas WHERE sistema_id=%s", (sistema_id,))
    cur.execute("DELETE FROM sistemas WHERE id=%s RETURNING id", (sistema_id,))
    deleted = cur.fetchone()
    conn.commit()
    conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Sistema não encontrado")
    return {"mensagem": "Sistema removido"}
