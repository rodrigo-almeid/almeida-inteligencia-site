# Almeida Inteligência — Portal Corporativo

Sistema interno modular para gestão de operações da Almeida Inteligência. Combina autenticação centralizada com módulos independentes de produtividade e automação.

---

## Arquitetura

```
internet
    │
  Cloudflare Tunnel (criptografia ponta a ponta)
    │
  nginx (container, porta 8080 no host → 80 interno)
    ├── /                     → Portal (landing + login)
    ├── /dashboard/           → Dashboard do usuário
    ├── /admin/               → Painel administrativo
    ├── /api/                 → Auth backend (FastAPI + PostgreSQL)
    ├── /email/               → Classificador de E-mails (FastAPI)
    ├── /central/             → API dos módulos centrais (FastAPI)
    ├── /credenciais/         → Frontend: Gerenciador de Credenciais
    ├── /financeiro/          → Frontend: Automação Financeira
    ├── /assistente/          → Assistente Virtual (Goku) — webhook + API
    ├── /assistente-painel/   → Frontend: Config do Assistente
    ├── /agendamento/         → Agendamento Inteligente — webhook + API
    └── /agendamento-painel/  → Frontend: Config do Agendamento
```

### Serviços Docker

| Container | Porta interna | Descrição |
|-----------|--------------|-----------|
| `almeida-inteligencia` | 80 | Nginx reverse proxy + frontend estático |
| `almeida-backend` | 8001 | Portal: auth, usuários, perfis, sistemas |
| `email-backend` | 8000 | Classificador de e-mails + ML |
| `central-backend` | 8000 | Módulos centrais: financeiro, credenciais, assistente, agendamento |
| `almeida-db` | 5432 | PostgreSQL 15 (compartilhado por todos os backends) |

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
| Assistente Virtual (Goku) | `/assistente/` | Bot WhatsApp multi-LLM para registro financeiro e consultas |
| Agendamento Inteligente | `/agendamento/` | Bot WhatsApp para agendamento com Google Calendar |

---

## Stack Técnica

- **Frontend:** HTML/CSS/JS vanilla, nginx 1.27-alpine
- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.0
- **Banco de dados:** PostgreSQL 15-alpine
- **Autenticação:** JWT (python-jose), bcrypt
- **Criptografia de senhas:** Fernet (cryptography)
- **ML:** scikit-learn (TF-IDF + Logistic Regression), NLTK
- **LLMs:** Gemini, Groq, Ollama (multi-provider com fallback)
- **Relatórios:** ReportLab (PDF), openpyxl (Excel)
- **Infraestrutura:** Docker Compose, Cloudflare Tunnel, GitHub Actions CI/CD

---

## CI/CD

O deploy é **automático via GitHub Actions**. A cada push na branch `main`:

1. **Testes unitários** — pytest com cobertura (central_backend)
2. **Deploy** — webhook dispara rebuild no servidor via `curl` com token seguro
3. **Testes de integração** — Newman (Postman) roda contra a API em produção

O workflow está em `.github/workflows/deploy.yml`.

### Fluxo no servidor

O deploy webhook no servidor executa:
```bash
cd ~/almeida-inteligencia-site
git pull
sudo docker compose up -d --build
```

### Secrets do GitHub Actions

| Secret | Descrição |
|--------|-----------|
| `DEPLOY_TOKEN` | Token de autenticação do webhook de deploy |

---

## Configuração do Ambiente

### Pré-requisitos no servidor

- Docker + Docker Compose
- Cloudflare Tunnel (`cloudflared`) configurado e rodando como serviço
- Arquivo `.env` na raiz do projeto (não commitado)

### Variáveis de ambiente (.env)

O `docker-compose.yml` referencia variáveis do arquivo `.env`. Copie o `.env.example` e preencha:

```bash
cp .env.example .env
nano .env
```

Para gerar chaves seguras:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

O `.env` está no `.gitignore` e **nunca deve ser commitado**. Se o deploy fizer `git clean`, o `.env` pode ser removido — verifique após deploys.

### Cloudflare Tunnel

Configuração em `/etc/cloudflared/config.yml`:
```yaml
tunnel: <tunnel-id>
credentials-file: /home/rodrigo/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: deploy.almeidainteligencia.com.br
    service: http://localhost:9000
  - hostname: almeidainteligencia.com.br
    service: http://localhost:8080
  - service: http_status:404
```

O Tunnel já fornece criptografia ponta a ponta — não é necessário SSL no nginx.

### Acesso ao banco (DBeaver)

O PostgreSQL está exposto apenas em `127.0.0.1:5432` (localhost do servidor). Para acessar remotamente, use SSH Tunnel no DBeaver:

1. **Aba SSH:** Host = IP do servidor, User = rodrigo, Auth = senha ou chave
2. **Aba Principal:** Host = `localhost`, Porta = `5432`, Banco = `almeida`, User = `almeida`

---

## Deploy Manual

```bash
git clone https://github.com/rodrigo-almeid/almeida-inteligencia-site.git
cd almeida-inteligencia-site
cp .env.example .env
nano .env  # preencher com valores reais
sudo docker compose up -d --build

# Logs
sudo docker compose logs -f

# Rebuild de um serviço específico
sudo docker compose up -d --build central-backend
```

---

## Testes

```bash
# central_backend (~110 testes, SQLite in-memory)
cd central_backend
pip install -r requirements-test.txt
pytest tests/ --cov=backend --cov-report=term-missing

# backend portal (~25 testes)
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
| [`.env.example`](.env.example) | Template de variáveis de ambiente |

---

## Segurança

### Medidas implementadas

- **Segredos fora do código** — todas as chaves, senhas e tokens ficam no `.env` (não commitado), referenciados via `${VAR}` no docker-compose
- **Deploy token protegido** — GitHub Actions usa `secrets.DEPLOY_TOKEN` em vez de token hardcoded
- **PostgreSQL sem porta exposta na internet** — bind em `127.0.0.1:5432`, acessível apenas via SSH tunnel
- **CORS restrito** — origens permitidas configuráveis via env var (não mais `allow_origins=["*"]`)
- **Rate limiting** — register (5/min) e login (10/min) via slowapi
- **Webhooks validados** — assinatura HMAC SHA-256 (`X-Hub-Signature-256`) no webhook do Assistente/Goku (Meta WhatsApp Cloud API), verificada contra `WHATSAPP_APP_SECRET`
- **SECRET_KEY sem fallback** — backend falha na inicialização se a chave não existir
- **Erros internos não expostos** — mensagens de erro do banco retornam "Erro interno do servidor"
- **JWT com validade reduzida** — tokens expiram em 30 minutos (módulos centrais e email)
- **Logs sanitizados** — mensagens do WhatsApp, telefones e respostas da IA não são mais logados
- **Hash do admin protegido** — removido do init.sql, criação via seed.py
- **Headers de segurança** — X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy
- **Senhas de usuários** — hash bcrypt (cost 12)
- **Senhas de sistemas** — criptografia Fernet (AES-128-CBC)
- **Controle de acesso** — RBAC por perfil no portal + autenticação por módulo
- **Criptografia em trânsito** — Cloudflare Tunnel (HTTPS automático para o usuário)
