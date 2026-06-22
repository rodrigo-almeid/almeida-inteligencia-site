"""Testes do módulo assistente virtual: /assistente/config e /assistente/webhook."""
import pytest


CONFIG_BASE = {
    "whatsapp_token": "EAAxxxxx",
    "whatsapp_phone_id": "123456789",
    "whatsapp_verify_token": "goku_verify_2024",
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
        """O response não deve expor whatsapp_token nem gemini_api_key."""
        client.post("/assistente/config", json=CONFIG_BASE, headers=auth_headers)
        res = client.get("/assistente/config", headers=auth_headers)
        data = res.json()
        assert "whatsapp_token" not in data
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


class TestWebhookVerificacao:
    def test_verificar_webhook_success(self, client, auth_headers, db, user):
        from backend.core.models import AssistenteConfig
        config = AssistenteConfig(
            whatsapp_verify_token="meu_token_secreto",
            ativo=True,
            user_id=user.id,
        )
        db.add(config)
        db.commit()

        res = client.get("/assistente/webhook", params={
            "hub.mode": "subscribe",
            "hub.verify_token": "meu_token_secreto",
            "hub.challenge": "desafio123",
        })
        assert res.status_code == 200
        assert res.text == "desafio123"

    def test_verificar_webhook_token_invalido(self, client):
        res = client.get("/assistente/webhook", params={
            "hub.mode": "subscribe",
            "hub.verify_token": "token_errado",
            "hub.challenge": "desafio",
        })
        assert res.status_code == 403

    def test_verificar_webhook_sem_mode(self, client):
        res = client.get("/assistente/webhook", params={
            "hub.verify_token": "qualquer",
            "hub.challenge": "desafio",
        })
        assert res.status_code == 403

    def test_verificar_webhook_config_inativa(self, client, auth_headers, db, user):
        from backend.core.models import AssistenteConfig
        config = AssistenteConfig(
            whatsapp_verify_token="token_inativo",
            ativo=False,
            user_id=user.id,
        )
        db.add(config)
        db.commit()

        res = client.get("/assistente/webhook", params={
            "hub.mode": "subscribe",
            "hub.verify_token": "token_inativo",
            "hub.challenge": "desafio",
        })
        assert res.status_code == 403


class TestWebhookMensagens:
    def test_post_sem_mensagens_retorna_ok(self, client):
        res = client.post("/assistente/webhook", json={
            "entry": [{"changes": [{"value": {"metadata": {}}}]}]
        })
        assert res.status_code == 200

    def test_post_body_vazio_retorna_ok(self, client):
        res = client.post("/assistente/webhook", json={"entry": [{"changes": [{"value": {}}]}]})
        assert res.status_code == 200

    def test_post_numero_nao_autorizado(self, client, db, user):
        from backend.core.models import AssistenteConfig
        config = AssistenteConfig(
            whatsapp_phone_id="999",
            whatsapp_token="token",
            numero_autorizado="5500000000000",
            ativo=True,
            user_id=user.id,
        )
        db.add(config)
        db.commit()

        res = client.post("/assistente/webhook", json={
            "entry": [{"changes": [{"value": {
                "metadata": {"phone_number_id": "999"},
                "messages": [{"from": "5511111111111", "type": "text", "text": {"body": "oi"}}]
            }}]}]
        })
        assert res.status_code == 200
