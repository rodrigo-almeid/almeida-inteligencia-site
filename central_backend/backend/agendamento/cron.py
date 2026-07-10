import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from backend.core import models
from backend.core.database import SessionLocal
from backend.assistente.whatsapp import enviar_mensagem
from backend.agendamento.google_sync import sync_from_google, setup_watch_channel


def limpar_pre_reservas_expiradas():
    db = SessionLocal()
    try:
        agora = datetime.utcnow()
        expirados = db.query(models.Appointment).filter(
            models.Appointment.status == "pre_reservado",
            models.Appointment.expires_at != None,
            models.Appointment.expires_at < agora,
        ).all()

        for appt in expirados:
            appt.status = "expirado"

        if expirados:
            db.commit()
            print(f"[cron] {len(expirados)} pré-reserva(s) expirada(s)")
    finally:
        db.close()


def enviar_lembretes():
    db = SessionLocal()
    try:
        agora = datetime.utcnow()
        limite = agora + timedelta(hours=2)

        pendentes = db.query(models.Appointment).filter(
            models.Appointment.status == "confirmado",
            models.Appointment.lembrete_enviado == False,
            models.Appointment.data_hora >= agora,
            models.Appointment.data_hora <= limite,
        ).all()

        for appt in pendentes:
            config = db.query(models.AgendamentoConfig).filter(
                models.AgendamentoConfig.id == appt.config_id,
            ).first()
            if not config or not config.ativo:
                continue

            assistente_cfg = db.query(models.AssistenteConfig).filter(
                models.AssistenteConfig.user_id == config.user_id,
            ).first()
            if not assistente_cfg or not assistente_cfg.ativo or not assistente_cfg.evolution_url:
                continue

            client = db.query(models.Client).filter(
                models.Client.id == appt.client_id,
            ).first()
            if not client:
                continue

            servico = db.query(models.Service).filter(
                models.Service.id == appt.service_id,
            ).first()
            nome_servico = servico.nome if servico else "seu agendamento"

            horario = appt.data_hora.strftime("%d/%m/%Y às %H:%M")
            texto = (
                f"Olá{', ' + client.nome if client.nome else ''}! "
                f"Lembramos que você tem {nome_servico} agendado para {horario}. "
                f"Nos vemos em breve!"
            )

            try:
                asyncio.get_event_loop().run_until_complete(
                    enviar_mensagem(
                        assistente_cfg.evolution_url, assistente_cfg.evolution_api_key,
                        assistente_cfg.evolution_instance, client.telefone, texto,
                    )
                )
            except RuntimeError:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(
                    enviar_mensagem(
                        assistente_cfg.evolution_url, assistente_cfg.evolution_api_key,
                        assistente_cfg.evolution_instance, client.telefone, texto,
                    )
                )
                loop.close()

            appt.lembrete_enviado = True

        if pendentes:
            db.commit()
            print(f"[cron] {len(pendentes)} lembrete(s) enviado(s)")
    finally:
        db.close()


def sync_google_calendars():
    db = SessionLocal()
    try:
        configs = db.query(models.AgendamentoConfig).filter(
            models.AgendamentoConfig.google_calendar_ativo == True,
            models.AgendamentoConfig.google_calendar_token != None,
        ).all()

        for config in configs:
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(sync_from_google(config, db))
                loop.close()
            except Exception as e:
                print(f"[cron] Erro sync Google config #{config.id}: {e}")

        if configs:
            print(f"[cron] Google Calendar sync: {len(configs)} tenant(s)")
    finally:
        db.close()


def renovar_google_channels():
    import os
    db = SessionLocal()
    try:
        agora = datetime.utcnow()
        limite = agora + timedelta(hours=24)

        configs = db.query(models.AgendamentoConfig).filter(
            models.AgendamentoConfig.google_calendar_ativo == True,
            models.AgendamentoConfig.google_calendar_token != None,
            models.AgendamentoConfig.google_calendar_channel_expiry != None,
            models.AgendamentoConfig.google_calendar_channel_expiry < limite,
        ).all()

        base_url = os.getenv("APP_BASE_URL", "")
        for config in configs:
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(setup_watch_channel(config, db, base_url))
                loop.close()
            except Exception as e:
                print(f"[cron] Erro renovar channel config #{config.id}: {e}")

        if configs:
            print(f"[cron] Renovados {len(configs)} Google Calendar channel(s)")
    finally:
        db.close()
