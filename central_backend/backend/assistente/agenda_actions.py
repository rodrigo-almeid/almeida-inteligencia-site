"""Consulta real de agenda — usada tanto pela tool consultar_agenda (pipeline
de tool-calling) quanto pelo roteamento legado por intenção. Nunca inventa
compromisso: só reporta o que existe de verdade em Appointment."""
from datetime import datetime, timedelta

from backend.core import models


def montar_resumo_agenda(config: models.AgendamentoConfig, client: models.Client, db, dias: int = 30) -> str:
    if not config.ativo:
        return "O módulo de agendamento não está ativo — nenhum compromisso é gerenciado por aqui."

    agora = datetime.utcnow()
    limite = agora + timedelta(days=dias)

    compromissos = db.query(models.Appointment).filter(
        models.Appointment.config_id == config.id,
        models.Appointment.status.in_(["confirmado", "pre_reservado"]),
        models.Appointment.data_hora >= agora - timedelta(hours=1),
        models.Appointment.data_hora <= limite,
    ).order_by(models.Appointment.data_hora).all()

    if not compromissos:
        return f"Nenhum compromisso confirmado ou pré-reservado nos próximos {dias} dias."

    linhas = [f"Compromissos nos próximos {dias} dias:"]
    for appt in compromissos:
        servico = db.query(models.Service).filter(models.Service.id == appt.service_id).first()
        nome_servico = servico.nome if servico else (appt.descricao or "Compromisso")
        status_txt = "confirmado" if appt.status == "confirmado" else "pré-reservado (aguardando confirmação)"
        linhas.append(f"  - {appt.data_hora.strftime('%d/%m %H:%M')} — {nome_servico} ({status_txt})")
    return "\n".join(linhas)
