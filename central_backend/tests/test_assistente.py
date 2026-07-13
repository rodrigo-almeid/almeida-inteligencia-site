"""Testes do módulo assistente virtual: /assistente/config e /assistente/webhook."""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.core.models import AssistenteConfig, Conta, CompraSupermercado
from backend.assistente.routers.webhook import (
    salvar_registro_financeiro, salvar_compra_mercado_de_texto, _eh_compra_de_mercado,
)
from backend.agendamento.crypto import decrypt_key


CONFIG_BASE = {
    "whatsapp_token": "test-whatsapp-token",
    "whatsapp_phone_id": "123456789012345",
    "whatsapp_verify_token": "test-verify-token",
    "gemini_api_key": "AIzaSyXXXXX",
    "numero_autorizado": "5543999211099",
    "nome_assistente": "Goku",
    "personalidade": "Seja direto e objetivo.",
    "tom_voz": "casual",
    "instrucoes_extras": "Classifique fast food como lazer.",
    "ativo": True,
}


class TestCriarConfig:
    def test_criar_config_success(self, client, auth_headers):
        res = client.post("/assistente/config", json=CONFIG_BASE, headers=auth_headers)
        assert res.status_code == 201
        data = res.json()
        assert data["nome_assistente"] == "Goku"
        assert data["tom_voz"] == "casual"
        assert data["ativo"] is True
        assert data["numero_autorizado"] == "5543999211099"
        assert "id" in data

    def test_criar_config_sem_auth(self, client):
        res = client.post("/assistente/config", json=CONFIG_BASE)
        assert res.status_code == 401

    def test_criar_config_duplicada(self, client, auth_headers):
        client.post("/assistente/config", json=CONFIG_BASE, headers=auth_headers)
        res = client.post("/assistente/config", json=CONFIG_BASE, headers=auth_headers)
        assert res.status_code == 400

    def test_criar_config_minima(self, client, auth_headers):
        res = client.post("/assistente/config", json={"ativo": False}, headers=auth_headers)
        assert res.status_code == 201
        data = res.json()
        assert data["nome_assistente"] == "Goku"
        assert data["tom_voz"] == "casual"
        assert data["ativo"] is False


class TestLerConfig:
    def test_ler_config_success(self, client, auth_headers):
        client.post("/assistente/config", json=CONFIG_BASE, headers=auth_headers)
        res = client.get("/assistente/config", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["nome_assistente"] == "Goku"
        assert data["personalidade"] == "Seja direto e objetivo."
        assert data["instrucoes_extras"] == "Classifique fast food como lazer."

    def test_ler_config_inexistente(self, client, auth_headers):
        res = client.get("/assistente/config", headers=auth_headers)
        assert res.status_code == 404

    def test_ler_config_sem_auth(self, client):
        res = client.get("/assistente/config")
        assert res.status_code == 401

    def test_isolamento_entre_usuarios(self, client, auth_headers, auth_headers2):
        client.post("/assistente/config", json=CONFIG_BASE, headers=auth_headers)
        res = client.get("/assistente/config", headers=auth_headers2)
        assert res.status_code == 404

    def test_config_nao_expoe_tokens(self, client, auth_headers):
        """O response não deve expor gemini_api_key."""
        client.post("/assistente/config", json=CONFIG_BASE, headers=auth_headers)
        res = client.get("/assistente/config", headers=auth_headers)
        data = res.json()
        assert "gemini_api_key" not in data


class TestAtualizarConfig:
    def test_atualizar_config_success(self, client, auth_headers):
        client.post("/assistente/config", json=CONFIG_BASE, headers=auth_headers)
        res = client.put("/assistente/config", json={
            **CONFIG_BASE,
            "nome_assistente": "Vegeta",
            "tom_voz": "formal",
        }, headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["nome_assistente"] == "Vegeta"
        assert res.json()["tom_voz"] == "formal"

    def test_atualizar_config_inexistente(self, client, auth_headers):
        res = client.put("/assistente/config", json=CONFIG_BASE, headers=auth_headers)
        assert res.status_code == 404

    def test_atualizar_sem_auth(self, client):
        res = client.put("/assistente/config", json=CONFIG_BASE)
        assert res.status_code == 401

    def test_atualizar_ativo(self, client, auth_headers):
        client.post("/assistente/config", json={**CONFIG_BASE, "ativo": False}, headers=auth_headers)
        res = client.put("/assistente/config", json={**CONFIG_BASE, "ativo": True}, headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["ativo"] is True


def _meta_payload(phone_id: str, from_number: str, texto: str) -> dict:
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": phone_id},
                    "messages": [{"from": from_number, "type": "text", "text": {"body": texto}}],
                },
            }],
        }],
    }


class TestWebhookVerify:
    def test_verify_sucesso_retorna_challenge(self, client, db, user):
        config = AssistenteConfig(
            whatsapp_phone_id="123456789012345",
            whatsapp_token="token-cifrado-fake",
            whatsapp_verify_token="meu-verify-token",
            ativo=True,
            user_id=user.id,
        )
        db.add(config)
        db.commit()

        res = client.get("/assistente/webhook", params={
            "hub.mode": "subscribe",
            "hub.verify_token": "meu-verify-token",
            "hub.challenge": "12345",
        })
        assert res.status_code == 200
        assert res.text == "12345"

    def test_verify_token_invalido(self, client, db, user):
        config = AssistenteConfig(
            whatsapp_phone_id="123456789012345",
            whatsapp_token="token-cifrado-fake",
            whatsapp_verify_token="meu-verify-token",
            ativo=True,
            user_id=user.id,
        )
        db.add(config)
        db.commit()

        res = client.get("/assistente/webhook", params={
            "hub.mode": "subscribe",
            "hub.verify_token": "token-errado",
            "hub.challenge": "12345",
        })
        assert res.status_code == 403

    def test_verify_mode_invalido(self, client):
        res = client.get("/assistente/webhook", params={
            "hub.mode": "unsubscribe",
            "hub.verify_token": "qualquer",
            "hub.challenge": "12345",
        })
        assert res.status_code == 403


class TestWebhookMensagens:
    def test_post_sem_campo_messages_e_ignorado(self, client):
        """Notificações de status (delivered/read) não têm 'messages' no value."""
        res = client.post("/assistente/webhook", json={
            "entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "x"}, "statuses": []}}]}],
        })
        assert res.status_code == 200
        assert res.json()["status"] == "ignored"

    def test_post_phone_id_desconhecido(self, client):
        """Rota é pública (exposta pelo nginx) — phone_number_id sem config correspondente não autentica."""
        res = client.post("/assistente/webhook", json=_meta_payload("999999999999999", "5511111111111", "oi"))
        assert res.status_code == 200
        assert res.json()["status"] == "unauthorized"

    def test_post_numero_nao_autorizado(self, client, db, user):
        config = AssistenteConfig(
            whatsapp_phone_id="123456789012345",
            whatsapp_token="token-cifrado-fake",
            numero_autorizado="5500000000000",
            ativo=True,
            user_id=user.id,
        )
        db.add(config)
        db.commit()

        res = client.post("/assistente/webhook", json=_meta_payload("123456789012345", "5511111111111", "oi"))
        assert res.status_code == 200
        assert res.json()["status"] == "unauthorized"

    def test_post_mensagem_autorizada_processa_e_responde(self, client, db, user):
        from backend.agendamento.crypto import encrypt_key
        config = AssistenteConfig(
            whatsapp_phone_id="123456789012345",
            whatsapp_token=encrypt_key("token-real"),
            numero_autorizado="5500000000000",
            usar_tool_calling=False,
            ativo=True,
            user_id=user.id,
        )
        db.add(config)
        db.commit()

        with patch("backend.assistente.routers.webhook.enviar_mensagem", new=AsyncMock()) as mock_enviar, \
             patch("backend.assistente.routers.webhook.detectar_intencao", new=AsyncMock(return_value="outro")), \
             patch("backend.assistente.routers.webhook.chat", new=AsyncMock(return_value="Oi, tudo bem?")):
            res = client.post("/assistente/webhook", json=_meta_payload("123456789012345", "5500000000000", "oi"))

        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        mock_enviar.assert_called_once()
        args = mock_enviar.call_args.args
        assert args[0] == "token-real"
        assert args[1] == "123456789012345"
        assert args[2] == "5500000000000"


class TestMascaramentoDeChaves:
    def test_whatsapp_token_mascarado_no_get(self, client, auth_headers):
        client.post("/assistente/config", json=CONFIG_BASE, headers=auth_headers)
        res = client.get("/assistente/config", headers=auth_headers)
        data = res.json()
        assert data["whatsapp_token"] != CONFIG_BASE["whatsapp_token"]
        assert CONFIG_BASE["whatsapp_token"] not in data["whatsapp_token"]

    def test_provedores_llm_api_key_mascarada_no_get(self, client, auth_headers):
        payload = {
            **CONFIG_BASE,
            "provedores_llm": [{"tipo": "gemini", "api_key": "AIzaSyREALKEY1234567890", "ativo": True}],
        }
        client.post("/assistente/config", json=payload, headers=auth_headers)
        res = client.get("/assistente/config", headers=auth_headers)
        chave_retornada = res.json()["provedores_llm"][0]["api_key"]
        assert chave_retornada != "AIzaSyREALKEY1234567890"
        assert "REALKEY" not in chave_retornada

    def test_atualizar_sem_mudar_chave_mascarada_preserva_valor_real(self, client, auth_headers, db):
        payload = {
            **CONFIG_BASE,
            "provedores_llm": [{"tipo": "gemini", "api_key": "AIzaSyREALKEY1234567890", "ativo": True}],
        }
        client.post("/assistente/config", json=payload, headers=auth_headers)

        get_res = client.get("/assistente/config", headers=auth_headers)
        provedores_mascarados = get_res.json()["provedores_llm"]
        chave_mascarada_whatsapp = get_res.json()["whatsapp_token"]

        # Simula o painel reenviando o formulário sem o usuário ter tocado nas chaves
        put_payload = {
            **CONFIG_BASE,
            "whatsapp_token": chave_mascarada_whatsapp,
            "provedores_llm": provedores_mascarados,
        }
        put_res = client.put("/assistente/config", json=put_payload, headers=auth_headers)
        assert put_res.status_code == 200

        config = db.query(AssistenteConfig).first()
        assert decrypt_key(config.whatsapp_token) == CONFIG_BASE["whatsapp_token"]
        provedores_salvos = json.loads(config.provedores_llm)
        assert decrypt_key(provedores_salvos[0]["api_key"]) == "AIzaSyREALKEY1234567890"

    def test_validar_com_chaves_mascaradas_usa_valores_reais(self, client, auth_headers):
        """Regressão: /assistente/validar não pode testar com o valor mascarado
        (o '…' quebra encoding ASCII de header HTTP e nunca é uma chave válida)."""
        payload = {
            **CONFIG_BASE,
            "provedores_llm": [{"tipo": "gemini", "api_key": "AIzaSyREALKEY1234567890", "ativo": True}],
        }
        client.post("/assistente/config", json=payload, headers=auth_headers)

        get_res = client.get("/assistente/config", headers=auth_headers)
        chave_mascarada_whatsapp = get_res.json()["whatsapp_token"]
        chave_mascarada_gemini = get_res.json()["provedores_llm"][0]["api_key"]
        assert "…" in chave_mascarada_whatsapp
        assert "…" in chave_mascarada_gemini

        gemini_response = MagicMock()
        gemini_response.status_code = 200

        whatsapp_response = MagicMock()
        whatsapp_response.status_code = 200
        whatsapp_response.json.return_value = {"verified_name": "Goku"}

        with patch("backend.assistente.routers.config.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(return_value=gemini_response)
            mock_instance.get = AsyncMock(return_value=whatsapp_response)
            mock_client.return_value = mock_instance

            res = client.post("/assistente/validar", json={
                "gemini_api_key": chave_mascarada_gemini,
                "whatsapp_token": chave_mascarada_whatsapp,
                "whatsapp_phone_id": CONFIG_BASE["whatsapp_phone_id"],
            }, headers=auth_headers)

        assert res.status_code == 200
        data = res.json()
        gemini_result = next(r for r in data["resultados"] if r["nome"] == "Google Gemini")
        assert gemini_result["ok"] is True
        whatsapp_result = next(r for r in data["resultados"] if r["nome"] == "Meta WhatsApp")
        assert whatsapp_result["ok"] is True

        gemini_call_url = mock_instance.post.call_args.args[0]
        assert "AIzaSyREALKEY1234567890" in gemini_call_url
        assert "…" not in gemini_call_url

        whatsapp_call_headers = mock_instance.get.call_args.kwargs["headers"]
        assert whatsapp_call_headers["Authorization"] == "Bearer test-whatsapp-token"

    def test_atualizar_com_chave_nova_sobrescreve_valor_real(self, client, auth_headers, db):
        payload = {
            **CONFIG_BASE,
            "provedores_llm": [{"tipo": "gemini", "api_key": "AIzaSyREALKEY1234567890", "ativo": True}],
        }
        client.post("/assistente/config", json=payload, headers=auth_headers)

        put_payload = {
            **CONFIG_BASE,
            "whatsapp_token": "novo-whatsapp-token",
            "provedores_llm": [{"tipo": "gemini", "api_key": "AIzaSyNOVACHAVE000000", "ativo": True}],
        }
        client.put("/assistente/config", json=put_payload, headers=auth_headers)

        config = db.query(AssistenteConfig).first()
        assert decrypt_key(config.whatsapp_token) == "novo-whatsapp-token"
        provedores_salvos = json.loads(config.provedores_llm)
        assert decrypt_key(provedores_salvos[0]["api_key"]) == "AIzaSyNOVACHAVE000000"


class TestListarModelosOllama:
    def test_lista_modelos_com_sucesso(self, client, auth_headers):
        ollama_response = MagicMock()
        ollama_response.status_code = 200
        ollama_response.json.return_value = {"models": [{"name": "goku:latest"}, {"name": "goku:ss1"}]}

        with patch("backend.assistente.routers.config.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(return_value=ollama_response)
            mock_client.return_value = mock_instance

            res = client.get("/assistente/ollama/modelos?url=http://localhost:11434", headers=auth_headers)

        assert res.status_code == 200
        assert res.json()["modelos"] == ["goku:latest", "goku:ss1"]

    def test_lista_modelos_ollama_indisponivel(self, client, auth_headers):
        import httpx as httpx_module

        with patch("backend.assistente.routers.config.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(side_effect=httpx_module.ConnectError("recusado"))
            mock_client.return_value = mock_instance

            res = client.get("/assistente/ollama/modelos?url=http://localhost:11434", headers=auth_headers)

        assert res.status_code == 502

    def test_lista_modelos_sem_auth(self, client):
        res = client.get("/assistente/ollama/modelos?url=http://localhost:11434")
        assert res.status_code == 401


class TestRegistroDeMercadoPorTexto:
    """Gasto de mercado relatado por texto (ex: 'gastei 45 no mercado no pix')
    deve cair no módulo Mercado, igual já acontece com foto de nota fiscal."""

    DADOS_MERCADO = {
        "descricao": "mercado", "valor": 45.0, "natureza": "despesa",
        "categoria": "alimentacao", "estabelecimento": "Mercado Bom Preço",
        "data": "2026-07-09", "status": "paga", "forma_pagamento": "pix",
        "tipo_estabelecimento": "mercado",
    }

    def test_eh_compra_de_mercado_true(self):
        assert _eh_compra_de_mercado(self.DADOS_MERCADO) is True

    def test_eh_compra_de_mercado_false_quando_outro_estabelecimento(self):
        assert _eh_compra_de_mercado({**self.DADOS_MERCADO, "tipo_estabelecimento": "outro"}) is False

    def test_eh_compra_de_mercado_false_quando_receita(self):
        assert _eh_compra_de_mercado({**self.DADOS_MERCADO, "natureza": "receita"}) is False

    def test_mercado_no_pix_cria_so_compra_supermercado(self, db, user):
        salvar_registro_financeiro(self.DADOS_MERCADO, user, db)

        compras = db.query(CompraSupermercado).filter(CompraSupermercado.user_id == user.id).all()
        assert len(compras) == 1
        assert compras[0].valor_total == 45.0
        assert compras[0].loja == "Mercado Bom Preço"
        assert compras[0].forma_pagamento == "pix"

        assert db.query(Conta).filter(Conta.user_id == user.id).count() == 0

    def test_mercado_no_debito_cria_compra_e_conta(self, db, user):
        """Espelha o fluxo de nota fiscal: débito também lança em Contas."""
        dados = {**self.DADOS_MERCADO, "forma_pagamento": "debito"}
        salvar_registro_financeiro(dados, user, db)

        assert db.query(CompraSupermercado).filter(CompraSupermercado.user_id == user.id).count() == 1

        contas = db.query(Conta).filter(Conta.user_id == user.id).all()
        assert len(contas) == 1
        assert contas[0].valor == 45.0

    def test_nao_mercado_cria_so_conta(self, db, user):
        dados = {**self.DADOS_MERCADO, "descricao": "almoço", "estabelecimento": "Restaurante X", "tipo_estabelecimento": "outro"}
        salvar_registro_financeiro(dados, user, db)

        assert db.query(CompraSupermercado).filter(CompraSupermercado.user_id == user.id).count() == 0
        assert db.query(Conta).filter(Conta.user_id == user.id).count() == 1

    def test_receita_ignora_flag_mercado(self, db, user):
        dados = {**self.DADOS_MERCADO, "descricao": "reembolso do mercado", "natureza": "receita"}
        salvar_registro_financeiro(dados, user, db)

        assert db.query(CompraSupermercado).filter(CompraSupermercado.user_id == user.id).count() == 0
        assert db.query(Conta).filter(Conta.user_id == user.id).count() == 1

    def test_sem_tipo_estabelecimento_continua_indo_pra_conta(self, db, user):
        """Compatibilidade: dados sem o campo novo (ex: pendente antigo) não quebram."""
        dados = {
            "descricao": "presente", "valor": 100.0, "natureza": "despesa",
            "categoria": "outros", "data": "2026-07-09", "status": "paga",
            "forma_pagamento": "credito",
        }
        salvar_registro_financeiro(dados, user, db)

        assert db.query(CompraSupermercado).filter(CompraSupermercado.user_id == user.id).count() == 0
        assert db.query(Conta).filter(Conta.user_id == user.id).count() == 1


class TestConsultarAgendaSemAlucinacao:
    """Regressão de bug real de produção (2026-07-10): perguntar sobre a
    agenda no fluxo legado (usar_tool_calling=False) caía em chat() livre,
    que inventava compromissos que não existiam. consultar_agenda() precisa
    sempre responder só com dados reais de Appointment."""

    @pytest.mark.asyncio
    async def test_agenda_sem_compromissos_nao_inventa_nada(self, db, user, assistente_config, agendamento_config, agendamento_client):
        from backend.assistente.routers.webhook import processar_mensagem

        agendamento_config.ativo = True
        assistente_config.numero_autorizado = agendamento_client.telefone
        assistente_config.usar_tool_calling = False
        db.commit()

        msg = {"type": "text", "text": {"body": "tenho algo agendado pra hoje?"}, "from": agendamento_client.telefone}

        with patch("backend.assistente.routers.webhook.detectar_intencao", new=AsyncMock(return_value="agenda")), \
             patch("backend.assistente.routers.webhook._gerar", new=AsyncMock(side_effect=Exception("IA indisponível no teste"))):
            resposta = await processar_mensagem(msg, assistente_config, user, db)

        assert "Nenhum compromisso" in resposta
        assert "14h" not in resposta and "Reunião" not in resposta

    @pytest.mark.asyncio
    async def test_agenda_com_compromisso_real_usa_dado_do_banco(
        self, db, user, assistente_config, agendamento_config, agendamento_client, agendamento_servico,
    ):
        from backend.assistente.routers.webhook import processar_mensagem
        from backend.core.models import Appointment
        from datetime import datetime, timedelta

        agendamento_config.ativo = True
        assistente_config.numero_autorizado = agendamento_client.telefone
        assistente_config.usar_tool_calling = False
        db.commit()

        amanha = datetime.utcnow() + timedelta(days=1)
        appt = Appointment(
            data_hora=amanha, status="confirmado",
            config_id=agendamento_config.id, client_id=agendamento_client.id, service_id=agendamento_servico.id,
        )
        db.add(appt)
        db.commit()

        msg = {"type": "text", "text": {"body": "o que eu tenho marcado?"}, "from": agendamento_client.telefone}

        with patch("backend.assistente.routers.webhook.detectar_intencao", new=AsyncMock(return_value="agenda")), \
             patch("backend.assistente.routers.webhook._gerar", new=AsyncMock(side_effect=Exception("IA indisponível no teste"))):
            resposta = await processar_mensagem(msg, assistente_config, user, db)

        assert "Corte Masculino" in resposta

    @pytest.mark.asyncio
    async def test_agenda_cria_config_automaticamente_se_nao_existir(self, db, user, assistente_config):
        """Usuário nunca configurou agendamento — não pode quebrar, só dizer que está livre."""
        from backend.assistente.routers.webhook import processar_mensagem

        assistente_config.usar_tool_calling = False
        db.commit()

        msg = {"type": "text", "text": {"body": "tenho reunião hoje?"}, "from": assistente_config.numero_autorizado}

        with patch("backend.assistente.routers.webhook.detectar_intencao", new=AsyncMock(return_value="agenda")), \
             patch("backend.assistente.routers.webhook._gerar", new=AsyncMock(side_effect=Exception("IA indisponível no teste"))):
            resposta = await processar_mensagem(msg, assistente_config, user, db)

        assert "não está ativo" in resposta or "Nenhum compromisso" in resposta
