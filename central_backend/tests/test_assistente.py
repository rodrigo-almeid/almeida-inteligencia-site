"""Testes do módulo assistente virtual: /assistente/config e /assistente/webhook."""
import pytest


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
        res = client.post("/assistente/webhook", json={
            "event": "connection.update",
            "data": {},
        })
        assert res.status_code == 200
        assert res.json()["status"] == "ignored"

    def test_post_sem_config(self, client):
        res = client.post("/assistente/webhook", json={
            "event": "messages.upsert",
            "instance": "inexistente",
            "data": {
                "key": {"remoteJid": "5511111111111@s.whatsapp.net", "fromMe": False},
                "message": {"conversation": "oi"},
            }
        })
        assert res.status_code == 200

    def test_post_numero_nao_autorizado(self, client, db, user):
        from backend.core.models import AssistenteConfig
        config = AssistenteConfig(
            evolution_instance="goku",
            evolution_url="http://evolution-api:8080",
            evolution_api_key="key",
            numero_autorizado="5500000000000",
            ativo=True,
            user_id=user.id,
        )
        db.add(config)
        db.commit()

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
