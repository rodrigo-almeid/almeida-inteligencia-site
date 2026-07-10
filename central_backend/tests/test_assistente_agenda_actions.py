"""Testes de backend/assistente/agenda_actions.py — consulta de agenda que
usa só dados reais de Appointment, sem margem pra alucinação do LLM."""
from datetime import datetime, timedelta
from backend.core.models import Appointment
from backend.assistente.agenda_actions import montar_resumo_agenda


class TestMontarResumoAgenda:
    def test_modulo_inativo_retorna_aviso(self, db, agendamento_config, agendamento_client):
        agendamento_config.ativo = False
        db.commit()

        resumo = montar_resumo_agenda(agendamento_config, agendamento_client, db)
        assert "não está ativo" in resumo

    def test_sem_compromissos_nao_inventa_nada(self, db, agendamento_config, agendamento_client):
        agendamento_config.ativo = True
        db.commit()

        resumo = montar_resumo_agenda(agendamento_config, agendamento_client, db)
        assert "Nenhum compromisso" in resumo

    def test_lista_compromisso_confirmado_real(self, db, agendamento_config, agendamento_client, agendamento_servico):
        agendamento_config.ativo = True
        db.commit()

        amanha = datetime.utcnow() + timedelta(days=1)
        appt = Appointment(
            data_hora=amanha, status="confirmado",
            config_id=agendamento_config.id, client_id=agendamento_client.id, service_id=agendamento_servico.id,
        )
        db.add(appt)
        db.commit()

        resumo = montar_resumo_agenda(agendamento_config, agendamento_client, db)
        assert "Corte Masculino" in resumo
        assert "confirmado" in resumo

    def test_nao_lista_compromisso_cancelado(self, db, agendamento_config, agendamento_client, agendamento_servico):
        agendamento_config.ativo = True
        db.commit()

        amanha = datetime.utcnow() + timedelta(days=1)
        appt = Appointment(
            data_hora=amanha, status="cancelado",
            config_id=agendamento_config.id, client_id=agendamento_client.id, service_id=agendamento_servico.id,
        )
        db.add(appt)
        db.commit()

        resumo = montar_resumo_agenda(agendamento_config, agendamento_client, db)
        assert "Nenhum compromisso" in resumo

    def test_nao_lista_compromisso_de_outro_cliente(self, db, agendamento_config, agendamento_servico):
        """Isolamento: compromisso de outro Client não vaza no resumo deste cliente."""
        from backend.core.models import Client
        agendamento_config.ativo = True
        outro_cliente = Client(config_id=agendamento_config.id, telefone="5511888887777", nome="Outra Pessoa")
        meu_cliente = Client(config_id=agendamento_config.id, telefone="5543999211099", nome="Dono")
        db.add_all([outro_cliente, meu_cliente])
        db.commit()

        amanha = datetime.utcnow() + timedelta(days=1)
        appt = Appointment(
            data_hora=amanha, status="confirmado",
            config_id=agendamento_config.id, client_id=outro_cliente.id, service_id=agendamento_servico.id,
        )
        db.add(appt)
        db.commit()

        resumo = montar_resumo_agenda(agendamento_config, meu_cliente, db)
        assert "Nenhum compromisso" in resumo
