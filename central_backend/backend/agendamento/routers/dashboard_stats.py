from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.core import models
from backend.core.database import get_db
from backend.core.security import get_current_user

router = APIRouter(prefix="/agendamento", tags=["Agendamento - Dashboard"])


@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    config = db.query(models.AgendamentoConfig).filter(
        models.AgendamentoConfig.user_id == current_user.id
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada.")

    agora = datetime.utcnow()
    inicio_dia = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    fim_dia = inicio_dia + timedelta(days=1)
    inicio_mes = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    conversas_hoje = db.query(func.count(func.distinct(models.ConversationMessage.client_id))).filter(
        models.ConversationMessage.config_id == config.id,
        models.ConversationMessage.criado_em >= inicio_dia,
        models.ConversationMessage.criado_em < fim_dia,
    ).scalar() or 0

    agendamentos_hoje = db.query(func.count(models.Appointment.id)).filter(
        models.Appointment.config_id == config.id,
        models.Appointment.data_hora >= inicio_dia,
        models.Appointment.data_hora < fim_dia,
        models.Appointment.status == "confirmado",
    ).scalar() or 0

    total_mes = db.query(func.count(models.Appointment.id)).filter(
        models.Appointment.config_id == config.id,
        models.Appointment.data_hora >= inicio_mes,
        models.Appointment.status.in_(["confirmado", "concluido"]),
    ).scalar() or 0

    ultimo_log = db.query(models.LlmLog).filter(
        models.LlmLog.config_id == config.id,
        models.LlmLog.status_code == 200,
    ).order_by(models.LlmLog.criado_em.desc()).first()

    proximos = db.query(models.Appointment).filter(
        models.Appointment.config_id == config.id,
        models.Appointment.data_hora >= agora,
        models.Appointment.status == "confirmado",
    ).order_by(models.Appointment.data_hora).limit(5).all()

    return {
        "conversas_hoje": conversas_hoje,
        "agendamentos_confirmados_hoje": agendamentos_hoje,
        "total_agendamentos_mes": total_mes,
        "ultima_llm_usada": ultimo_log.provider if ultimo_log else None,
        "proximos_agendamentos": [
            {
                "id": a.id,
                "data_hora": a.data_hora.isoformat(),
                "client_id": a.client_id,
                "service_id": a.service_id,
                "status": a.status,
            }
            for a in proximos
        ],
    }
