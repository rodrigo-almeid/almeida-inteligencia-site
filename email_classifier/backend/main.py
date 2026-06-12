from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import backend.core.models      # registra tabela users
import backend.emails.models    # registra tabelas de e-mail

from backend.core.database import engine, Base
from backend.emails.routers.auth import router as auth_router
from backend.emails.routers.emails import router as emails_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Email Manager", version="1.0.0")

app.include_router(auth_router)
app.include_router(emails_router)

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
