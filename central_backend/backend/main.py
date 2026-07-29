import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from backend.core.database import engine
from backend.core import models
import backend.criador.models  # noqa: F401 — registra tabelas criador no mesmo Base

from backend.auth.routers import auth, perfis as perfis_router
from backend.credenciais.routers import senhas, pessoas, csv as csv_router
from backend.financeiro.routers import contas, categorias, dividas, recorrencias, relatorios, cartoes, faturas, itens_fatura, pagamentos_fatura
from backend.combustivel.routers import abastecimentos
from backend.mercado.routers import compras as mercado_compras
from backend.assistente.routers import config as assistente_config, webhook as assistente_webhook, simulador as assistente_simulador
from backend.criador import router as criador_router
from backend.agendamento.routers import (
    config as agendamento_config,
    horarios as agendamento_horarios,
    servicos as agendamento_servicos,
    clients as agendamento_clients,
    appointments as agendamento_appointments,
    dashboard_stats as agendamento_stats,
    google_calendar as agendamento_google,
)

models.Base.metadata.create_all(bind=engine)

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from backend.core.rate_limit import limiter
from backend.core.webhook_security import WebhookSignatureMiddleware

app = FastAPI(title="Almeida — Módulos Centrais", docs_url=None, redoc_url=None, openapi_url=None)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(WebhookSignatureMiddleware)


@app.on_event("startup")
def start_scheduler():
    import os
    if os.getenv("TESTING"):
        return
    from apscheduler.schedulers.background import BackgroundScheduler
    from backend.agendamento.cron import limpar_pre_reservas_expiradas, enviar_lembretes, sync_google_calendars, renovar_google_channels
    scheduler = BackgroundScheduler()
    scheduler.add_job(limpar_pre_reservas_expiradas, "interval", minutes=1)
    scheduler.add_job(enviar_lembretes, "interval", minutes=30)
    scheduler.add_job(sync_google_calendars, "interval", minutes=15)
    scheduler.add_job(renovar_google_channels, "interval", hours=12)
    scheduler.start()

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8080").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
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
app.include_router(cartoes.router)
app.include_router(faturas.router)
app.include_router(itens_fatura.router)
app.include_router(pagamentos_fatura.router)

# Combustível
app.include_router(abastecimentos.router)

# Mercado
app.include_router(mercado_compras.router)

# Assistente Virtual (Goku)
app.include_router(assistente_config.router)
app.include_router(assistente_webhook.router)
app.include_router(assistente_simulador.router)

# Agendamento Inteligente
app.include_router(agendamento_config.router)
app.include_router(agendamento_horarios.router)
app.include_router(agendamento_servicos.router)
app.include_router(agendamento_clients.router)
app.include_router(agendamento_appointments.router)
app.include_router(agendamento_stats.router)
app.include_router(agendamento_google.router)

# Modo Criador
app.include_router(criador_router.router)

# Frontends estáticos
import pathlib as _pathlib
_media_path = _pathlib.Path(os.getenv("MEDIA_DIR", "/app/media/transcricoes"))
_media_path.mkdir(parents=True, exist_ok=True)
app.mount("/media/transcricoes", StaticFiles(directory=str(_media_path)), name="media_transcricoes")

app.mount("/shared", StaticFiles(directory="frontend/shared"), name="shared")
app.mount("/credenciais", StaticFiles(directory="frontend/credenciais", html=True), name="credenciais")
app.mount("/financeiro",  StaticFiles(directory="frontend/financeiro",  html=True), name="financeiro")
app.mount("/assistente-painel", StaticFiles(directory="frontend/assistente", html=True), name="assistente-painel")
app.mount("/agendamento-painel", StaticFiles(directory="frontend/agendamento", html=True), name="agendamento-painel")
