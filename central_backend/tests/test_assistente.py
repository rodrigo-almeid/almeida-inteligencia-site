"""Testes do módulo assistente virtual: /assistente/config e /assistente/webhook."""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.core.models import AssistenteConfig, Conta, CompraSupermercado
from backend.assistente.routers.webhook import (
    salvar_registro_financeiro, salvar_compra_mercado_de_texto, _eh_compra_de_mercado,
)


CONFIG_BASE = {
    "evolution_url": "http://evolution-api:8080",
    "evolution_api_key": "test-api-key",
    "evolution_instance": "goku",
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


class TestWebhookMensagens:
    def test_post_evento_ignorado(self, client):
        """Eventos que não são messages.upsert são ignorados mesmo sem secret."""
        res = client.post("/assistente/webhook", json={
            "event": "connection.update",
            "data": {},
        })
        assert res.status_code == 200
        assert res.json()["status"] == "ignored"

    def test_post_sem_secret(self, client):
        """Rota é pública (exposta pelo nginx) — sem secret, não autentica."""
        res = client.post("/assistente/webhook", json={
            "event": "messages.upsert",
            "instance": "goku",
            "data": {
                "key": {"remoteJid": "5511111111111@s.whatsapp.net", "fromMe": False},
                "message": {"conversation": "oi"},
            }
        })
        assert res.status_code == 200
        assert res.json()["status"] == "unauthorized"

    def test_post_secret_invalido(self, client, db, user):
        config = AssistenteConfig(
            evolution_instance="goku",
            evolution_url="http://evolution-api:8080",
            evolution_api_key="key",
            numero_autorizado="5500000000000",
            webhook_secret="segredo-correto",
            ativo=True,
            user_id=user.id,
        )
        db.add(config)
        db.commit()

        res = client.post("/assistente/webhook?secret=segredo-errado", json={
            "event": "messages.upsert",
            "data": {
                "key": {"remoteJid": "5500000000000@s.whatsapp.net", "fromMe": False},
                "message": {"conversation": "oi"},
            }
        })
        assert res.status_code == 200
        assert res.json()["status"] == "unauthorized"

    def test_post_numero_nao_autorizado(self, client, db, user):
        config = AssistenteConfig(
            evolution_instance="goku",
            evolution_url="http://evolution-api:8080",
            evolution_api_key="key",
            numero_autorizado="5500000000000",
            webhook_secret="segredo-correto",
            ativo=True,
            user_id=user.id,
        )
        db.add(config)
        db.commit()

        res = client.post("/assistente/webhook?secret=segredo-correto", json={
            "event": "messages.upsert",
            "data": {
                "key": {"remoteJid": "5511111111111@s.whatsapp.net", "fromMe": False},
                "message": {"conversation": "oi"},
            }
        })
        assert res.status_code == 200
        assert res.json()["status"] == "unauthorized"


class TestWebhookSecret:
    def test_webhook_secret_gerado_automaticamente(self, client, auth_headers, db):
        client.post("/assistente/config", json=CONFIG_BASE, headers=auth_headers)
        config = db.query(AssistenteConfig).first()
        assert config.webhook_secret
        assert len(config.webhook_secret) >= 16

    def test_webhook_secret_nao_aparece_na_resposta(self, client, auth_headers):
        res = client.post("/assistente/config", json=CONFIG_BASE, headers=auth_headers)
        assert "webhook_secret" not in res.json()
        res_get = client.get("/assistente/config", headers=auth_headers)
        assert "webhook_secret" not in res_get.json()


class TestMascaramentoDeChaves:
    def test_evolution_api_key_mascarada_no_get(self, client, auth_headers):
        client.post("/assistente/config", json=CONFIG_BASE, headers=auth_headers)
        res = client.get("/assistente/config", headers=auth_headers)
        data = res.json()
        assert data["evolution_api_key"] != CONFIG_BASE["evolution_api_key"]
        assert CONFIG_BASE["evolution_api_key"] not in data["evolution_api_key"]

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
        chave_mascarada_evolution = get_res.json()["evolution_api_key"]

        # Simula o painel reenviando o formulário sem o usuário ter tocado nas chaves
        put_payload = {
            **CONFIG_BASE,
            "evolution_api_key": chave_mascarada_evolution,
            "provedores_llm": provedores_mascarados,
        }
        put_res = client.put("/assistente/config", json=put_payload, headers=auth_headers)
        assert put_res.status_code == 200

        config = db.query(AssistenteConfig).first()
        assert config.evolution_api_key == CONFIG_BASE["evolution_api_key"]
        provedores_salvos = json.loads(config.provedores_llm)
        assert provedores_salvos[0]["api_key"] == "AIzaSyREALKEY1234567890"

    def test_validar_com_chaves_mascaradas_usa_valores_reais(self, client, auth_headers):
        """Regressão: /assistente/validar não pode testar com o valor mascarado
        (o '…' quebra encoding ASCII de header HTTP e nunca é uma chave válida)."""
        payload = {
            **CONFIG_BASE,
            "provedores_llm": [{"tipo": "gemini", "api_key": "AIzaSyREALKEY1234567890", "ativo": True}],
        }
        client.post("/assistente/config", json=payload, headers=auth_headers)

        get_res = client.get("/assistente/config", headers=auth_headers)
        chave_mascarada_evolution = get_res.json()["evolution_api_key"]
        chave_mascarada_gemini = get_res.json()["provedores_llm"][0]["api_key"]
        assert "…" in chave_mascarada_evolution
        assert "…" in chave_mascarada_gemini

        gemini_response = MagicMock()
        gemini_response.status_code = 200

        evolution_response = MagicMock()
        evolution_response.status_code = 200
        evolution_response.json.return_value = {"instance": {"state": "open"}}

        with patch("backend.assistente.routers.config.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(return_value=gemini_response)
            mock_instance.get = AsyncMock(return_value=evolution_response)
            mock_client.return_value = mock_instance

            res = client.post("/assistente/validar", json={
                "gemini_api_key": chave_mascarada_gemini,
                "evolution_api_key": chave_mascarada_evolution,
                "evolution_url": CONFIG_BASE["evolution_url"],
                "evolution_instance": CONFIG_BASE["evolution_instance"],
            }, headers=auth_headers)

        assert res.status_code == 200
        data = res.json()
        gemini_result = next(r for r in data["resultados"] if r["nome"] == "Google Gemini")
        assert gemini_result["ok"] is True
        evolution_result = next(r for r in data["resultados"] if r["nome"] == "Evolution API")
        assert evolution_result["ok"] is True

        gemini_call_url = mock_instance.post.call_args.args[0]
        assert "AIzaSyREALKEY1234567890" in gemini_call_url
        assert "…" not in gemini_call_url

        evolution_call_headers = mock_instance.get.call_args.kwargs["headers"]
        assert evolution_call_headers["apikey"] == "test-api-key"

    def test_atualizar_com_chave_nova_sobrescreve_valor_real(self, client, auth_headers, db):
        payload = {
            **CONFIG_BASE,
            "provedores_llm": [{"tipo": "gemini", "api_key": "AIzaSyREALKEY1234567890", "ativo": True}],
        }
        client.post("/assistente/config", json=payload, headers=auth_headers)

        put_payload = {
            **CONFIG_BASE,
            "evolution_api_key": "nova-evolution-key",
            "provedores_llm": [{"tipo": "gemini", "api_key": "AIzaSyNOVACHAVE000000", "ativo": True}],
        }
        client.put("/assistente/config", json=put_payload, headers=auth_headers)

        config = db.query(AssistenteConfig).first()
        assert config.evolution_api_key == "nova-evolution-key"
        provedores_salvos = json.loads(config.provedores_llm)
        assert provedores_salvos[0]["api_key"] == "AIzaSyNOVACHAVE000000"


class TestDesconectar:
    def test_desconectar_com_sessao_ativa_faz_logout(self, client, auth_headers):
        client.post("/assistente/config", json=CONFIG_BASE, headers=auth_headers)

        logout_response = MagicMock()
        logout_response.is_success = True

        with patch("backend.assistente.routers.config.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.delete = AsyncMock(return_value=logout_response)
            mock_client.return_value = mock_instance

            res = client.post("/assistente/desconectar", headers=auth_headers)

        assert res.status_code == 200
        assert res.json()["status"] == "desconectado"
        mock_instance.delete.assert_called_once()
        assert "/instance/logout/" in mock_instance.delete.call_args.args[0]

    def test_desconectar_com_sessao_travada_apaga_instancia(self, client, auth_headers):
        """Regressão: sessão derrubada pelo WhatsApp (conflict/device_removed) fica
        'not connected' — logout falha com 400, precisa cair pro delete da instância
        pra parar o loop de reconexão automática."""
        client.post("/assistente/config", json=CONFIG_BASE, headers=auth_headers)

        logout_response = MagicMock()
        logout_response.is_success = False
        logout_response.status_code = 400
        logout_response.text = '{"message":["The instance is not connected"]}'

        delete_response = MagicMock()
        delete_response.is_success = True

        with patch("backend.assistente.routers.config.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.delete = AsyncMock(side_effect=[logout_response, delete_response])
            mock_client.return_value = mock_instance

            res = client.post("/assistente/desconectar", headers=auth_headers)

        assert res.status_code == 200
        assert res.json()["status"] == "instancia_removida"
        assert mock_instance.delete.call_count == 2

    def test_desconectar_sem_config(self, client, auth_headers):
        res = client.post("/assistente/desconectar", headers=auth_headers)
        assert res.status_code == 404


class TestWebhookResync:
    def test_resync_atualiza_webhook_sem_gerar_qrcode(self, client, auth_headers, db):
        client.post("/assistente/config", json=CONFIG_BASE, headers=auth_headers)

        state_response = MagicMock()
        state_response.status_code = 200

        webhook_set_response = MagicMock()
        webhook_set_response.is_success = True

        with patch("backend.assistente.routers.config.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(return_value=state_response)
            mock_instance.post = AsyncMock(return_value=webhook_set_response)
            mock_client.return_value = mock_instance

            res = client.post("/assistente/webhook/resync", headers=auth_headers)

        assert res.status_code == 200
        assert res.json()["status"] == "ok"

        # Só chamou connectionState (get) e webhook/set (post) — nunca instance/connect
        get_urls = [c.args[0] for c in mock_instance.get.call_args_list]
        assert all("instance/connect/" not in u for u in get_urls)
        mock_instance.post.assert_called_once()
        assert "/webhook/set/" in mock_instance.post.call_args.args[0]


class TestGarantirInstanceWebhook:
    """Regressão: sem 'enabled': true, a Evolution API aceita o /webhook/set mas
    nunca dispara o webhook — mensagens reais chegam e são silenciosamente ignoradas."""

    def test_qrcode_configura_webhook_com_enabled_true_e_secret(self, client, auth_headers, db):
        client.post("/assistente/config", json=CONFIG_BASE, headers=auth_headers)

        state_response = MagicMock()
        state_response.status_code = 200

        webhook_set_response = MagicMock()
        webhook_set_response.is_success = True

        connect_response = MagicMock()
        connect_response.is_success = True
        connect_response.json.return_value = {"code": "fake-qrcode"}

        with patch("backend.assistente.routers.config.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(side_effect=[state_response, connect_response])
            mock_instance.post = AsyncMock(return_value=webhook_set_response)
            mock_client.return_value = mock_instance

            res = client.get("/assistente/qrcode", headers=auth_headers)

        assert res.status_code == 200

        webhook_payload = mock_instance.post.call_args.kwargs["json"]["webhook"]
        assert webhook_payload["enabled"] is True
        assert "secret=" in webhook_payload["url"]

        config = db.query(AssistenteConfig).first()
        assert config.webhook_secret in webhook_payload["url"]


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
