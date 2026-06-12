"""Testes do endpoint de exportação CSV de credenciais."""
import pytest
import csv
import io
import os
from cryptography.fernet import Fernet


def _inserir_senha(db, pessoa, sistema="GitHub", usuario="dev@teste.com", senha_plain="SenhaGitHub@1"):
    from backend.core.models import Senha
    fernet = Fernet(os.environ["FERNET_SECRET_KEY"].encode())
    s = Senha(
        sistema=sistema,
        usuario_sistema=usuario,
        senha_criptografada=fernet.encrypt(senha_plain.encode()).decode(),
        pessoa_id=pessoa.id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


class TestExportarCSV:
    def test_exporta_csv_autenticado(self, client, auth_headers, pessoa, db):
        _inserir_senha(db, pessoa)
        res = client.get("/exportar-csv", headers=auth_headers)
        assert res.status_code == 200
        assert "text/csv" in res.headers["content-type"]

    def test_exporta_csv_sem_auth(self, client):
        res = client.get("/exportar-csv")
        assert res.status_code == 401

    def test_csv_nao_contem_senha(self, client, auth_headers, pessoa, db):
        """Coluna Senha_Criptografada não deve mais existir no CSV após correção do bug."""
        _inserir_senha(db, pessoa, senha_plain="SenhaSuperSecreta")
        res = client.get("/exportar-csv", headers=auth_headers)
        content = res.content.decode("utf-8")
        reader = csv.reader(io.StringIO(content))
        header = next(reader)
        # Verifica que a coluna de senha foi removida
        assert "Senha_Criptografada" not in header
        assert "Senha" not in header

    def test_csv_conteudo_correto(self, client, auth_headers, pessoa, db):
        _inserir_senha(db, pessoa, sistema="BitBucket", usuario="eng@company.com")
        res = client.get("/exportar-csv", headers=auth_headers)
        content = res.content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) >= 1
        sistemas = [r["Sistema"] for r in rows]
        usuarios = [r["Usuario"] for r in rows]
        assert "BitBucket" in sistemas
        assert "eng@company.com" in usuarios

    def test_csv_isolamento_usuarios(self, client, auth_headers2, pessoa, db):
        """Usuário 2 não vê credenciais do usuário 1 no CSV."""
        _inserir_senha(db, pessoa, sistema="Segredo")
        res = client.get("/exportar-csv", headers=auth_headers2)
        content = res.content.decode("utf-8")
        assert "Segredo" not in content

    def test_csv_vazio_sem_credenciais(self, client, auth_headers):
        res = client.get("/exportar-csv", headers=auth_headers)
        assert res.status_code == 200
        content = res.content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        assert list(reader) == []
