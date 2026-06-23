import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from backend.core import models
from backend.core.database import SessionLocal
from backend.agendamento.whatsapp import enviar_mensagem


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
                    enviar_mensagem(config.whatsapp_token, config.whatsapp_phone_id, client.telefone, texto)
                )
            except RuntimeError:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(
                    enviar_mensagem(config.whatsapp_token, config.whatsapp_phone_id, client.telefone, texto)
                )
                loop.close()

            appt.lembrete_enviado = True

        if pendentes:
            db.commit()
            print(f"[cron] {len(pendentes)} lembrete(s) enviado(s)")
    finally:
        db.close()
