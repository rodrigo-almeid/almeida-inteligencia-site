"""Testes das tools de agenda pessoal: marcar direto (sem passo de
confirmação separado) e atualizar o assunto de um compromisso já marcado."""
import pytest
from datetime import datetime, timedelta

from backend.core.models import Appointment
from backend.assistente.adapters.base import ToolCall
from backend.assistente import tools_agendamento as tools


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


class TestMarcarCompromisso:
    @pytest.mark.asyncio
    async def test_marca_direto_ja_confirmado_sem_passo_extra(self, db, agendamento_config, agendamento_client, agendamento_servico):
        amanha_14h = (datetime.utcnow() + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
        tc = ToolCall(name="marcar_compromisso", arguments={
            "service_id": agendamento_servico.id, "data_hora": _fmt(amanha_14h),
        })

        resultado = await tools.executar(tc, agendamento_config, agendamento_client, db)

        appt = db.query(Appointment).filter(Appointment.config_id == agendamento_config.id).first()
        assert appt is not None
        assert appt.status == "confirmado"
        assert appt.expires_at is None
        assert "marcado" in resultado.lower()
        assert f"#{appt.id}" not in resultado
        assert "ID" not in resultado

    @pytest.mark.asyncio
    async def test_marca_com_assunto_salva_descricao(self, db, agendamento_config, agendamento_client, agendamento_servico):
        amanha_14h = (datetime.utcnow() + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
        tc = ToolCall(name="marcar_compromisso", arguments={
            "service_id": agendamento_servico.id, "data_hora": _fmt(amanha_14h), "descricao": "Falar sobre o projeto X",
        })

        await tools.executar(tc, agendamento_config, agendamento_client, db)

        appt = db.query(Appointment).filter(Appointment.config_id == agendamento_config.id).first()
        assert appt.descricao == "Falar sobre o projeto X"

    @pytest.mark.asyncio
    async def test_conflito_de_horario_nao_marca_por_cima(self, db, agendamento_config, agendamento_client, agendamento_servico):
        amanha_14h = (datetime.utcnow() + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
        db.add(Appointment(
            data_hora=amanha_14h, status="confirmado",
            config_id=agendamento_config.id, client_id=agendamento_client.id, service_id=agendamento_servico.id,
        ))
        db.commit()

        tc = ToolCall(name="marcar_compromisso", arguments={
            "service_id": agendamento_servico.id, "data_hora": _fmt(amanha_14h),
        })
        resultado = await tools.executar(tc, agendamento_config, agendamento_client, db)

        assert "conflito" in resultado.lower()
        total = db.query(Appointment).filter(Appointment.config_id == agendamento_config.id).count()
        assert total == 1  # não criou um segundo compromisso em cima do primeiro

    @pytest.mark.asyncio
    async def test_pre_reserva_expirada_libera_o_horario(self, db, agendamento_config, agendamento_client, agendamento_servico):
        amanha_14h = (datetime.utcnow() + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
        db.add(Appointment(
            data_hora=amanha_14h, status="pre_reservado",
            expires_at=datetime.utcnow() - timedelta(minutes=1),
            config_id=agendamento_config.id, client_id=agendamento_client.id, service_id=agendamento_servico.id,
        ))
        db.commit()

        tc = ToolCall(name="marcar_compromisso", arguments={
            "service_id": agendamento_servico.id, "data_hora": _fmt(amanha_14h),
        })
        resultado = await tools.executar(tc, agendamento_config, agendamento_client, db)

        assert "conflito" not in resultado.lower()
        confirmados = db.query(Appointment).filter(Appointment.status == "confirmado").count()
        assert confirmados == 1


class TestAtualizarCompromisso:
    @pytest.mark.asyncio
    async def test_atualiza_assunto_por_data_hora_exata(self, db, agendamento_config, agendamento_client, agendamento_servico):
        amanha_14h = (datetime.utcnow() + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
        appt = Appointment(
            data_hora=amanha_14h, status="confirmado",
            config_id=agendamento_config.id, client_id=agendamento_client.id, service_id=agendamento_servico.id,
        )
        db.add(appt)
        db.commit()

        tc = ToolCall(name="atualizar_compromisso", arguments={
            "descricao": "Assunto X", "data_hora": _fmt(amanha_14h),
        })
        resultado = await tools.executar(tc, agendamento_config, agendamento_client, db)

        db.refresh(appt)
        assert appt.descricao == "Assunto X"
        assert "Assunto X" in resultado

    @pytest.mark.asyncio
    async def test_atualiza_proximo_compromisso_sem_data_hora(self, db, agendamento_config, agendamento_client, agendamento_servico):
        amanha = (datetime.utcnow() + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        appt = Appointment(
            data_hora=amanha, status="confirmado",
            config_id=agendamento_config.id, client_id=agendamento_client.id, service_id=agendamento_servico.id,
        )
        db.add(appt)
        db.commit()

        tc = ToolCall(name="atualizar_compromisso", arguments={"descricao": "Revisão de contrato"})
        await tools.executar(tc, agendamento_config, agendamento_client, db)

        db.refresh(appt)
        assert appt.descricao == "Revisão de contrato"

    @pytest.mark.asyncio
    async def test_sem_compromisso_retorna_aviso(self, db, agendamento_config, agendamento_client):
        tc = ToolCall(name="atualizar_compromisso", arguments={"descricao": "Assunto qualquer"})
        resultado = await tools.executar(tc, agendamento_config, agendamento_client, db)
        assert "não encontrei" in resultado.lower()
