import os
import httpx
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.core import models
from backend.core.database import get_db, SessionLocal
from backend.core.security import get_current_user
from backend.agendamento.crypto import encrypt_key, decrypt_key
from backend.agendamento.google_sync import sync_from_google, setup_watch_channel, stop_watch_channel

router = APIRouter(prefix="/agendamento/google", tags=["Agendamento - Google Calendar"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"
SCOPES = "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/calendar.readonly"


def _get_redirect_uri(request: Request) -> str:
    base = os.getenv("APP_BASE_URL", str(request.base_url).rstrip("/"))
    return f"{base}/agendamento/google/callback"


@router.get("/auth-url")
def get_auth_url(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID não configurado no servidor.")

    state = encrypt_key(f"{current_user.id}")
    redirect_uri = _get_redirect_uri(request)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }

    return {"url": f"{GOOGLE_AUTH_URL}?{urlencode(params)}"}


@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    db: Session = Depends(get_db),
):
    if error:
        return RedirectResponse(f"/assistente-painel/?google=error&msg={error}")

    if not code or not state:
        return RedirectResponse("/assistente-painel/?google=error&msg=missing_params")

    try:
        user_id = int(decrypt_key(state))
    except Exception:
        return RedirectResponse("/assistente-painel/?google=error&msg=invalid_state")

    try:
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        redirect_uri = _get_redirect_uri(request)

        async with httpx.AsyncClient(timeout=15) as client:
            token_res = await client.post(GOOGLE_TOKEN_URL, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            })

        if token_res.status_code != 200:
            print(f"[gcal] token exchange falhou: {token_res.status_code} {token_res.text[:300]}")
            return RedirectResponse("/assistente-painel/?google=error&msg=token_exchange_failed")

        token_data = token_res.json()
        refresh_token = token_data.get("refresh_token")
        access_token = token_data.get("access_token")

        if not refresh_token:
            return RedirectResponse("/assistente-painel/?google=error&msg=no_refresh_token")

        async with httpx.AsyncClient(timeout=10) as client:
            cal_res = await client.get(
                f"{GOOGLE_CALENDAR_API}/calendars/primary",
                headers={"Authorization": f"Bearer {access_token}"},
            )

        calendar_id = "primary"
        if cal_res.status_code == 200:
            calendar_id = cal_res.json().get("id", "primary")

        config = db.query(models.AgendamentoConfig).filter(
            models.AgendamentoConfig.user_id == user_id
        ).first()

        if not config:
            # Conectar o Google Calendar não deveria depender de o usuário ter
            # salvo antes a aba de catálogo/negócio — cria a config vazia aqui,
            # igual o llm_gateway já faz na primeira mensagem processada.
            config = models.AgendamentoConfig(user_id=user_id, ativo=False)
            db.add(config)
            db.flush()

        config.google_calendar_token = encrypt_key(refresh_token)
        config.google_calendar_id = calendar_id
        config.google_calendar_ativo = True
        db.commit()

        base_url = os.getenv("APP_BASE_URL", str(request.base_url).rstrip("/"))
        await setup_watch_channel(config, db, base_url)

        return RedirectResponse("/assistente-painel/?google=ok")
    except Exception as e:
        import traceback
        print(f"[gcal] Erro inesperado no callback OAuth: {type(e).__name__}: {e}")
        traceback.print_exc()
        return RedirectResponse("/assistente-painel/?google=error&msg=erro_interno")


@router.post("/disconnect")
async def disconnect_google(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = db.query(models.AgendamentoConfig).filter(
        models.AgendamentoConfig.user_id == current_user.id
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada.")

    await stop_watch_channel(config, db)

    config.google_calendar_token = None
    config.google_calendar_id = None
    config.google_calendar_ativo = False
    config.google_calendar_sync_token = None
    config.google_calendar_channel_id = None
    config.google_calendar_channel_expiry = None
    db.commit()

    return {"ok": True, "mensagem": "Google Calendar desconectado."}


@router.post("/sync-now")
async def sync_now(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Sincronização manual sob demanda (botão 'Sincronizar agora' no calendário) —
    mesma função usada pelo cron de 15min e pelo webhook de push do Google."""
    config = db.query(models.AgendamentoConfig).filter(
        models.AgendamentoConfig.user_id == current_user.id
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada.")
    if not config.google_calendar_ativo:
        raise HTTPException(status_code=400, detail="Google Calendar não está conectado.")

    await sync_from_google(config, db)
    return {"ok": True}


@router.post("/webhook")
async def google_webhook(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    channel_id = request.headers.get("X-Goog-Channel-ID")
    channel_token = request.headers.get("X-Goog-Channel-Token", "")

    if not channel_token.startswith("config_"):
        return {"status": "ignored"}

    try:
        config_id = int(channel_token.replace("config_", ""))
    except ValueError:
        return {"status": "invalid token"}

    config = db.query(models.AgendamentoConfig).filter(
        models.AgendamentoConfig.id == config_id,
        models.AgendamentoConfig.google_calendar_ativo == True,
    ).first()

    if not config:
        return {"status": "config not found"}

    background_tasks.add_task(_sync_background, config_id)
    return {"status": "ok"}


async def _sync_background(config_id: int):
    db = SessionLocal()
    try:
        config = db.query(models.AgendamentoConfig).filter(
            models.AgendamentoConfig.id == config_id,
        ).first()
        if config:
            await sync_from_google(config, db)
    finally:
        db.close()
