import os
import uuid
import httpx
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from backend.core import models
from backend.agendamento.crypto import encrypt_key, decrypt_key

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"


async def get_access_token(config: models.AgendamentoConfig) -> str:
    refresh_token = decrypt_key(config.google_calendar_token)
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(GOOGLE_TOKEN_URL, data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })

    if res.status_code != 200:
        raise Exception(f"Google OAuth refresh failed: {res.text[:300]}")

    return res.json()["access_token"]


async def criar_evento_google(config: models.AgendamentoConfig, appointment: models.Appointment, db: Session):
    if not config.google_calendar_ativo or not config.google_calendar_token:
        return

    try:
        access_token = await get_access_token(config)
        calendar_id = config.google_calendar_id or "primary"

        service_obj = db.query(models.Service).filter(models.Service.id == appointment.service_id).first()

        nome_servico = service_obj.nome if service_obj else "Compromisso"
        duracao = service_obj.duracao_minutos if service_obj else 30

        start = appointment.data_hora
        end = start + timedelta(minutes=duracao)

        descricao_partes = [appointment.descricao] if appointment.descricao else []
        descricao_partes.append("Agendado via assistente WhatsApp")

        event = {
            "summary": nome_servico,
            "description": "\n\n".join(descricao_partes),
            "start": {"dateTime": start.isoformat(), "timeZone": "America/Sao_Paulo"},
            "end": {"dateTime": end.isoformat(), "timeZone": "America/Sao_Paulo"},
            "extendedProperties": {
                "private": {"almeida_appointment_id": str(appointment.id)},
            },
        }

        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(
                f"{GOOGLE_CALENDAR_API}/calendars/{calendar_id}/events",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json=event,
            )

        if res.status_code in (200, 201):
            appointment.google_event_id = res.json()["id"]
            db.commit()
            print(f"[gcal] Evento criado: {appointment.google_event_id}")
        else:
            print(f"[gcal] Erro ao criar evento: {res.status_code} {res.text[:200]}")
    except Exception as e:
        print(f"[gcal] Erro criar_evento_google: {e}")


async def cancelar_evento_google(config: models.AgendamentoConfig, appointment: models.Appointment, db: Session):
    if not config.google_calendar_ativo or not config.google_calendar_token:
        return
    if not appointment.google_event_id:
        return

    try:
        access_token = await get_access_token(config)
        calendar_id = config.google_calendar_id or "primary"

        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.delete(
                f"{GOOGLE_CALENDAR_API}/calendars/{calendar_id}/events/{appointment.google_event_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if res.status_code in (200, 204):
            print(f"[gcal] Evento cancelado: {appointment.google_event_id}")
            appointment.google_event_id = None
            db.commit()
        else:
            print(f"[gcal] Erro ao cancelar evento: {res.status_code}")
    except Exception as e:
        print(f"[gcal] Erro cancelar_evento_google: {e}")


async def atualizar_evento_google(config: models.AgendamentoConfig, appointment: models.Appointment, db: Session):
    if not config.google_calendar_ativo or not config.google_calendar_token:
        return
    if not appointment.google_event_id:
        return

    try:
        access_token = await get_access_token(config)
        calendar_id = config.google_calendar_id or "primary"

        service_obj = db.query(models.Service).filter(models.Service.id == appointment.service_id).first()
        duracao = service_obj.duracao_minutos if service_obj else 30

        start = appointment.data_hora
        end = start + timedelta(minutes=duracao)

        descricao_partes = [appointment.descricao] if appointment.descricao else []
        descricao_partes.append("Agendado via assistente WhatsApp")

        patch = {
            "start": {"dateTime": start.isoformat(), "timeZone": "America/Sao_Paulo"},
            "end": {"dateTime": end.isoformat(), "timeZone": "America/Sao_Paulo"},
            "description": "\n\n".join(descricao_partes),
        }

        async with httpx.AsyncClient(timeout=10) as client:
            await client.patch(
                f"{GOOGLE_CALENDAR_API}/calendars/{calendar_id}/events/{appointment.google_event_id}",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json=patch,
            )
    except Exception as e:
        print(f"[gcal] Erro atualizar_evento_google: {e}")


async def sync_from_google(config: models.AgendamentoConfig, db: Session):
    if not config.google_calendar_ativo or not config.google_calendar_token:
        return

    try:
        access_token = await get_access_token(config)
        calendar_id = config.google_calendar_id or "primary"

        params = {"singleEvents": "true", "maxResults": "100"}
        if config.google_calendar_sync_token:
            params["syncToken"] = config.google_calendar_sync_token
        else:
            params["timeMin"] = (datetime.utcnow() - timedelta(days=1)).isoformat() + "Z"

        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.get(
                f"{GOOGLE_CALENDAR_API}/calendars/{calendar_id}/events",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )

        if res.status_code == 410:
            config.google_calendar_sync_token = None
            db.commit()
            return await sync_from_google(config, db)

        if res.status_code != 200:
            print(f"[gcal] Sync error: {res.status_code}")
            return

        data = res.json()

        for event in data.get("items", []):
            event_id = event.get("id")
            status = event.get("status")

            appt = db.query(models.Appointment).filter(
                models.Appointment.config_id == config.id,
                models.Appointment.google_event_id == event_id,
            ).first()

            if appt:
                if status == "cancelled" and appt.status not in ("cancelado", "expirado"):
                    appt.status = "cancelado"
                    appt.google_event_id = None
                    print(f"[gcal] Appointment #{appt.id} cancelado via Google Calendar")
                elif status != "cancelled" and event.get("start"):
                    start_str = event["start"].get("dateTime", "")
                    if start_str:
                        new_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00")).replace(tzinfo=None)
                        if abs((new_dt - appt.data_hora).total_seconds()) > 60:
                            appt.data_hora = new_dt
                            print(f"[gcal] Appointment #{appt.id} reagendado via Google Calendar para {new_dt}")
            else:
                if status == "cancelled":
                    continue

                ext_props = event.get("extendedProperties", {}).get("private", {})
                if ext_props.get("almeida_appointment_id"):
                    continue

                start_data = event.get("start", {})
                start_str = start_data.get("dateTime", "")
                if not start_str:
                    continue

                new_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00")).replace(tzinfo=None)
                summary = event.get("summary", "Evento Google Calendar")

                default_client = db.query(models.Client).filter(
                    models.Client.config_id == config.id,
                    models.Client.telefone == "google_calendar",
                ).first()
                if not default_client:
                    default_client = models.Client(
                        config_id=config.id, telefone="google_calendar", nome="Evento Manual (Google)",
                    )
                    db.add(default_client)
                    db.flush()

                new_appt = models.Appointment(
                    config_id=config.id, client_id=default_client.id,
                    data_hora=new_dt, status="confirmado",
                    google_event_id=event_id,
                )
                db.add(new_appt)
                print(f"[gcal] Novo appointment criado de evento Google: {summary}")

        if data.get("nextSyncToken"):
            config.google_calendar_sync_token = data["nextSyncToken"]

        db.commit()

    except Exception as e:
        print(f"[gcal] Erro sync_from_google: {e}")
        import traceback
        traceback.print_exc()


async def setup_watch_channel(config: models.AgendamentoConfig, db: Session, base_url: str):
    if not config.google_calendar_ativo or not config.google_calendar_token:
        return

    try:
        access_token = await get_access_token(config)
        calendar_id = config.google_calendar_id or "primary"
        channel_id = str(uuid.uuid4())
        channel_token = f"config_{config.id}"

        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(
                f"{GOOGLE_CALENDAR_API}/calendars/{calendar_id}/events/watch",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json={
                    "id": channel_id,
                    "type": "web_hook",
                    "address": f"{base_url}/agendamento/google/webhook",
                    "token": channel_token,
                    "params": {"ttl": "2592000"},
                },
            )

        if res.status_code == 200:
            data = res.json()
            config.google_calendar_channel_id = channel_id
            expiry_ms = int(data.get("expiration", 0))
            if expiry_ms:
                config.google_calendar_channel_expiry = datetime.utcfromtimestamp(expiry_ms / 1000)
            db.commit()
            print(f"[gcal] Watch channel criado: {channel_id}")
        else:
            print(f"[gcal] Erro ao criar watch: {res.status_code} {res.text[:200]}")
    except Exception as e:
        print(f"[gcal] Erro setup_watch_channel: {e}")


async def stop_watch_channel(config: models.AgendamentoConfig, db: Session):
    if not config.google_calendar_channel_id or not config.google_calendar_token:
        return

    try:
        access_token = await get_access_token(config)
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{GOOGLE_CALENDAR_API}/channels/stop",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json={
                    "id": config.google_calendar_channel_id,
                    "resourceId": config.google_calendar_id or "primary",
                },
            )
        config.google_calendar_channel_id = None
        config.google_calendar_channel_expiry = None
        db.commit()
    except Exception as e:
        print(f"[gcal] Erro stop_watch_channel: {e}")
