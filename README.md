# Almeida Inteligência — Portal Corporativo

Sistema interno modular para gestão de operações da Almeida Inteligência. Combina autenticação centralizada com módulos independentes de produtividade e automação.

---

## Arquitetura

```
internet
    │
  nginx (porta 8080)
    ├── /                → Portal (landing + login)
    ├── /dashboard/      → Dashboard do usuário
    ├── /admin/          → Painel administrativo
    ├── /api/            → Auth backend (FastAPI + PostgreSQL)
    ├── /email/          → Classificador de E-mails (FastAPI + PostgreSQL)
    ├── /central/        → API dos módulos centrais (FastAPI + PostgreSQL)
    ├── /credenciais/    → Frontend: Gerenciador de Credenciais
    └── /financeiro/     → Frontend: Automação Financeira
```

### Serviços Docker

| Container | Porta interna | Banco |
|-----------|--------------|-------|
| `almeida-inteligencia` | 80 | — |
| `almeida-backend` | 8001 | `almeida-db` (PostgreSQL) |
| `email-backend` | 8000 | `email-db` (PostgreSQL) |
| `central-backend` | 8000 | `central-db` (PostgreSQL) |

---

## Módulos

| Módulo | Rota | Descrição |
|--------|------|-----------|
| Portal | `/` | Landing page + autenticação SSO |
| Admin | `/admin/` | Gestão de usuários, perfis e sistemas |
| Classificador de E-mails | `/email/` | Extração, classificação ML e triagem de e-mails IMAP |
| Gerenciador de Credenciais | `/credenciais/` | Cofre de senhas corporativas com criptografia Fernet |
| Automação Financeira | `/financeiro/` | Controle de contas, despesas, dívidas e relatórios |
| Combustível | `/central/abastecimentos/` | Registro e estatísticas de abastecimentos |

---

## Stack Técnica

- **Frontend:** HTML/CSS/JS vanilla, nginx 1.27-alpine
- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.0
- **Banco de dados:** PostgreSQL 15-alpine
- **Autenticação:** JWT (python-jose), bcrypt
- **Criptografia de senhas:** Fernet (cryptography)
- **ML:** scikit-learn (TF-IDF + Logistic Regression), NLTK
- **Relatórios:** ReportLab (PDF), openpyxl (Excel)
- **Infraestrutura:** Docker + Docker Compose

---

## Deploy

```bash
# Clonar e subir
git clone https://github.com/rodrigo-almeid/almeida-inteligencia-site.git
cd almeida-inteligencia-site
/usr/local/bin/docker-compose-v2 up -d --build

# Logs
/usr/local/bin/docker-compose-v2 logs -f

# Rebuild de um serviço específico
/usr/local/bin/docker-compose-v2 up -d --build central-backend
```

**Acesso:** `http://147.15.47.151:8080`

---

## Testes

```bash
# central_backend (~70 testes, SQLite in-memory)
cd central_backend
pip install -r requirements-test.txt
pytest tests/ --cov=backend --cov-report=term-missing

# backend portal (~25 testes, psycopg2 mockado)
cd backend
pip install -r requirements-test.txt
pytest tests/ --cov=main --cov-report=term-missing
```

---

## Documentação

| Arquivo | Conteúdo |
|---------|----------|
| [`docs/REQUISITOS.md`](docs/REQUISITOS.md) | Documento de requisitos funcionais e não-funcionais |
| [`docs/HISTORIAS_USUARIO.md`](docs/HISTORIAS_USUARIO.md) | Histórias de usuário (User Stories) |
| [`docs/BRANDBOOK.html`](docs/BRANDBOOK.html) | Identidade visual Almeida Inteligência |

---

## Segurança

- Senhas de usuários: hash bcrypt (cost 12)
- Senhas de sistemas: criptografia Fernet (AES-128-CBC)
- Tokens JWT: expiração configurável (padrão 8h portal / 8h módulos)
- Variáveis sensíveis: injetadas via Docker Compose environment (nunca commitadas)
- Controle de acesso: RBAC por perfil no portal + autenticação por módulo
