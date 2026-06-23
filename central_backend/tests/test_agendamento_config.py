"""Testes do módulo de agendamento: /agendamento/config."""
import pytest


CONFIG_BASE = {
    "whatsapp_token": "EAAxxxx",
    "whatsapp_phone_id": "111222333",
    "whatsapp_verify_token": "meu-verify",
    "gemini_api_key": "AIzaXXXX",
    "groq_api_key": "gsk_XXXX",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llama3",
    "prioridade_llms": '["gemini","groq","ollama"]',
    "gemini_ativo": True,
    "groq_ativo": False,
    "ollama_ativo": False,
    "catalogo_prompt": "Somos o Salão X.",
    "mensagem_midia_bloqueada": "Só texto.",
    "mensagem_contingencia": "Indisponível.",
    "ativo": True,
}


class TestCriarConfig:
    def test_criar_config_success(self, client, auth_headers):
        res = client.post("/agendamento/config", json=CONFIG_BASE, headers=auth_headers)
        assert res.status_code == 201
        data = res.json()
        assert data["ativo"] is True
        assert data["gemini_ativo"] is True
        assert data["whatsapp_phone_id"] == "111222333"
        assert "gemini_api_key_masked" in data

    def test_criar_config_sem_auth(self, client):
        res = client.post("/agendamento/config", json=CONFIG_BASE)
        assert res.status_code == 401

    def test_criar_config_duplicada(self, client, auth_headers):
        client.post("/agendamento/config", json=CONFIG_BASE, headers=auth_headers)
        res = client.post("/agendamento/config", json=CONFIG_BASE, headers=auth_headers)
        assert res.status_code == 400
        assert "já existe" in res.json()["detail"]


class TestGetConfig:
    def test_get_config_success(self, client, auth_headers, agendamento_config):
        res = client.get("/agendamento/config", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["ativo"] is True
        assert data["gemini_ativo"] is True

    def test_get_config_nao_existe(self, client, auth_headers):
        res = client.get("/agendamento/config", headers=auth_headers)
        assert res.status_code == 404

    def test_get_config_keys_mascaradas(self, client, auth_headers, agendamento_config):
        res = client.get("/agendamento/config", headers=auth_headers)
        data = res.json()
        assert data["gemini_api_key_masked"] is not None
        assert "***" in data["gemini_api_key_masked"]

    def test_get_config_sem_auth(self, client):
        res = client.get("/agendamento/config")
        assert res.status_code == 401


class TestAtualizarConfig:
    def test_atualizar_config_success(self, client, auth_headers, agendamento_config):
        payload = {**CONFIG_BASE, "catalogo_prompt": "Novo catálogo"}
        res = client.put("/agendamento/config", json=payload, headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["catalogo_prompt"] == "Novo catálogo"

    def test_atualizar_config_nao_existe(self, client, auth_headers):
        res = client.put("/agendamento/config", json=CONFIG_BASE, headers=auth_headers)
        assert res.status_code == 404

    def test_atualizar_toggle_llm(self, client, auth_headers, agendamento_config):
        payload = {**CONFIG_BASE, "groq_ativo": True, "ollama_ativo": True}
        res = client.put("/agendamento/config", json=payload, headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["groq_ativo"] is True
        assert res.json()["ollama_ativo"] is True

    def test_isolamento_config(self, client, auth_headers2, agendamento_config):
        """Usuário 2 não acessa config do usuário 1."""
        res = client.get("/agendamento/config", headers=auth_headers2)
        assert res.status_code == 404
