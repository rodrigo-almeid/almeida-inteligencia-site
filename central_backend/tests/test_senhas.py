"""Testes do gerenciador de credenciais: /me/senhas/."""
import pytest
from cryptography.fernet import Fernet
import os


def _fernet():
    return Fernet(os.environ["FERNET_SECRET_KEY"].encode())


class TestCriarSenha:
    def test_criar_credencial_success(self, client, auth_headers, pessoa):
        payload = {
            "sistema": "Gmail",
            "usuario_sistema": "user@gmail.com",
            "senha": "MinhaSenha@123",
            "pessoa_id": pessoa.id,
        }
        res = client.post("/me/senhas/", json=payload, headers=auth_headers)
        assert res.status_code == 200
        assert "mensagem" in res.json()

    def test_criar_credencial_armazena_criptografada(self, client, auth_headers, pessoa, db):
        from backend.core.models import Senha
        client.post(
            "/me/senhas/",
            json={"sistema": "AWS", "usuario_sistema": "admin", "senha": "Segredo@Aws1", "pessoa_id": pessoa.id},
            headers=auth_headers,
        )
        db.expire_all()
        s = db.query(Senha).filter_by(sistema="AWS").first()
        assert s is not None
        # Senha no banco deve ser diferente do texto plano
        assert s.senha_criptografada != "Segredo@Aws1"
        # Mas deve ser descriptografável com a chave correta
        decrypted = _fernet().decrypt(s.senha_criptografada.encode()).decode()
        assert decrypted == "Segredo@Aws1"

    def test_criar_credencial_sem_auth(self, client, pessoa):
        res = client.post("/me/senhas/", json={"sistema": "X", "usuario_sistema": "u", "senha": "s", "pessoa_id": pessoa.id})
        assert res.status_code == 401

    def test_criar_credencial_campos_obrigatorios(self, client, auth_headers):
        res = client.post("/me/senhas/", json={"sistema": "X"}, headers=auth_headers)
        assert res.status_code == 422


class TestListarSenhas:
    def test_listar_senhas_da_pessoa(self, client, auth_headers, pessoa, db):
        from backend.core.models import Senha
        fernet = _fernet()
        db.add(Senha(
            sistema="Banco", usuario_sistema="ana", pessoa_id=pessoa.id,
            senha_criptografada=fernet.encrypt(b"Banco@123").decode()
        ))
        db.commit()

        res = client.get(f"/me/senhas/{pessoa.id}", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["sistema"] == "Banco"
        # senha deve vir descriptografada pelo backend
        assert data[0]["senha_criptografada"] == "Banco@123"

    def test_listar_pessoa_de_outro_usuario(self, client, auth_headers, pessoa2):
        res = client.get(f"/me/senhas/{pessoa2.id}", headers=auth_headers)
        assert res.status_code == 403

    def test_listar_pessoa_inexistente(self, client, auth_headers):
        res = client.get("/me/senhas/99999", headers=auth_headers)
        assert res.status_code == 403

    def test_listar_sem_auth(self, client, pessoa):
        res = client.get(f"/me/senhas/{pessoa.id}")
        assert res.status_code == 401

    def test_listar_vazio(self, client, auth_headers, pessoa):
        res = client.get(f"/me/senhas/{pessoa.id}", headers=auth_headers)
        assert res.status_code == 200
        assert res.json() == []


class TestDeletarSenha:
    def _criar_senha(self, db, pessoa):
        from backend.core.models import Senha
        fernet = _fernet()
        s = Senha(
            sistema="Netflix",
            usuario_sistema="teste@gmail.com",
            senha_criptografada=fernet.encrypt(b"SenhaNetflix@1").decode(),
            pessoa_id=pessoa.id,
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        return s

    def test_deletar_credencial_success(self, client, auth_headers, pessoa, db):
        s = self._criar_senha(db, pessoa)
        res = client.delete(f"/me/senhas/credencial/{s.id}", headers=auth_headers)
        assert res.status_code == 200
        from backend.core.models import Senha
        db.expire_all()
        assert db.get(Senha, s.id) is None

    def test_deletar_credencial_de_outro_usuario(self, client, auth_headers, pessoa2, db):
        s = self._criar_senha(db, pessoa2)
        res = client.delete(f"/me/senhas/credencial/{s.id}", headers=auth_headers)
        assert res.status_code == 403

    def test_deletar_credencial_inexistente(self, client, auth_headers):
        res = client.delete("/me/senhas/credencial/99999", headers=auth_headers)
        assert res.status_code == 404

    def test_deletar_sem_auth(self, client, pessoa, db):
        s = self._criar_senha(db, pessoa)
        res = client.delete(f"/me/senhas/credencial/{s.id}")
        assert res.status_code == 401


class TestPerfilSenhas:
    """Testa /me/senhas/perfil/ — gestão de perfis dentro do módulo de senhas."""

    def test_listar_perfis_vazio(self, client, auth_headers):
        res = client.get("/me/senhas/perfil/", headers=auth_headers)
        assert res.status_code == 200
        assert res.json() == []

    def test_listar_perfis_com_dados(self, client, auth_headers, pessoa):
        res = client.get("/me/senhas/perfil/", headers=auth_headers)
        assert res.status_code == 200
        nomes = [p["nome"] for p in res.json()]
        assert pessoa.nome in nomes

    def test_criar_perfil(self, client, auth_headers):
        res = client.post("/me/senhas/perfil/", json={"nome": "Trabalho", "principal": False}, headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["nome"] == "Trabalho"

    def test_criar_primeiro_perfil_vira_principal(self, client, auth_headers):
        res = client.post("/me/senhas/perfil/", json={"nome": "Único", "principal": False}, headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["principal"] is True

    def test_criar_perfil_sem_auth(self, client):
        res = client.post("/me/senhas/perfil/", json={"nome": "X", "principal": False})
        assert res.status_code == 401

    def test_listar_perfis_sem_auth(self, client):
        res = client.get("/me/senhas/perfil/")
        assert res.status_code == 401


class TestSenhaDescryptInvalida:
    """Cobre o branch except da descriptografia de senhas com formato inválido."""

    def test_senha_formato_invalido_retorna_mensagem_erro(self, client, auth_headers, pessoa, db):
        from backend.core.models import Senha
        db.add(Senha(
            sistema="Antigo",
            usuario_sistema="u",
            senha_criptografada="nao-e-fernet-valido",
            pessoa_id=pessoa.id,
        ))
        db.commit()
        res = client.get(f"/me/senhas/{pessoa.id}", headers=auth_headers)
        assert res.status_code == 200
        creds = res.json()
        assert any("Erro" in c["senha_criptografada"] for c in creds)


class TestPropriedades:
    def test_adicionar_propriedade(self, client, auth_headers, pessoa):
        res = client.post(
            "/me/senhas/dados/",
            json={"chave": "CPF", "valor": "123.456.789-00", "pessoa_id": pessoa.id},
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert res.json()["chave"] == "CPF"

    def test_listar_propriedades(self, client, auth_headers, pessoa, db):
        from backend.core.models import DadoPessoal
        db.add(DadoPessoal(chave="RG", valor="1234567", pessoa_id=pessoa.id))
        db.commit()
        res = client.get(f"/me/senhas/propriedades/{pessoa.id}", headers=auth_headers)
        assert res.status_code == 200
        assert any(p["chave"] == "RG" for p in res.json())

    def test_deletar_propriedade(self, client, auth_headers, pessoa, db):
        from backend.core.models import DadoPessoal
        dp = DadoPessoal(chave="Temp", valor="valor", pessoa_id=pessoa.id)
        db.add(dp)
        db.commit()
        db.refresh(dp)
        res = client.delete(f"/me/senhas/dados/{dp.id}", headers=auth_headers)
        assert res.status_code == 200

    def test_propriedade_de_outro_usuario_negada(self, client, auth_headers, pessoa2, db):
        from backend.core.models import DadoPessoal
        dp = DadoPessoal(chave="Chave", valor="Valor", pessoa_id=pessoa2.id)
        db.add(dp)
        db.commit()
        db.refresh(dp)
        res = client.delete(f"/me/senhas/dados/{dp.id}", headers=auth_headers)
        assert res.status_code == 403

    def test_adicionar_propriedade_perfil_invalido(self, client, auth_headers, pessoa2):
        res = client.post(
            "/me/senhas/dados/",
            json={"chave": "X", "valor": "Y", "pessoa_id": pessoa2.id},
            headers=auth_headers,
        )
        assert res.status_code == 403

    def test_listar_propriedades_perfil_invalido(self, client, auth_headers, pessoa2):
        res = client.get(f"/me/senhas/propriedades/{pessoa2.id}", headers=auth_headers)
        assert res.status_code == 403

    def test_deletar_propriedade_inexistente(self, client, auth_headers):
        res = client.delete("/me/senhas/dados/99999", headers=auth_headers)
        assert res.status_code == 404
