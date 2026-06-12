from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from backend.core.database import engine
from backend.core import models

from backend.auth.routers import auth, perfis as perfis_router
from backend.credenciais.routers import senhas, pessoas, csv as csv_router
from backend.financeiro.routers import contas, categorias, dividas, recorrencias, relatorios
from backend.combustivel.routers import abastecimentos

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Almeida — Módulos Centrais", docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth
app.include_router(auth.router)
app.include_router(perfis_router.router)

# Credenciais
app.include_router(senhas.router)
app.include_router(pessoas.router)
app.include_router(csv_router.router)

# Financeiro
app.include_router(categorias.router)
app.include_router(contas.router)
app.include_router(dividas.router)
app.include_router(recorrencias.router)
app.include_router(relatorios.router)

# Combustível
app.include_router(abastecimentos.router)

# Frontends estáticos
app.mount("/credenciais", StaticFiles(directory="frontend/credenciais", html=True), name="credenciais")
app.mount("/financeiro",  StaticFiles(directory="frontend/financeiro",  html=True), name="financeiro")
