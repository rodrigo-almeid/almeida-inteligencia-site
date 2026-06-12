from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

load_dotenv()

from backend.core.database import engine
from backend.core import models

from backend.contas.routers import (
    auth, senhas, pessoas, contas, categorias,
    dividas, recorrencias, relatorios, abastecimentos,
    csv as csv_router, perfis as perfis_router,
)

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Almeida — Módulos Centrais", docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(perfis_router.router)
app.include_router(senhas.router)
app.include_router(pessoas.router)
app.include_router(categorias.router)
app.include_router(contas.router)
app.include_router(dividas.router)
app.include_router(recorrencias.router)
app.include_router(relatorios.router)
app.include_router(abastecimentos.router)
app.include_router(csv_router.router)

# Frontend estático — servido pelo FastAPI
app.mount("/credenciais", StaticFiles(directory="frontend/credenciais", html=True), name="credenciais")
app.mount("/financeiro",  StaticFiles(directory="frontend/financeiro",  html=True), name="financeiro")
