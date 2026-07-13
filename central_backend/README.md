# Central Sistemas — Almeida Inteligência

Plataforma modular para automação de processos pessoais e profissionais: gestão financeira, assistente virtual de WhatsApp (finanças + agendamento inteligente com IA), cofre de credenciais e mais.

---

## Sumário

- [Arquitetura](#arquitetura)
- [Módulos](#módulos)
  - [Portal Administrativo](#1-portal-administrativo)
  - [Automação Financeira](#2-automação-financeira)
  - [Assistente Virtual (Goku)](#3-assistente-virtual-goku)
  - [Gerenciador de Credenciais](#4-gerenciador-de-credenciais)
  - [Classificador de E-mails](#5-classificador-de-e-mails)
  - [Controle de Combustível](#6-controle-de-combustível)
  - [Controle de Mercado](#7-controle-de-mercado)
- [Integrações entre Módulos](#integrações-entre-módulos)
- [Instalação e Execução](#instalação-e-execução)
- [Variáveis de Ambiente](#variáveis-de-ambiente)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [API — Referência Rápida](#api--referência-rápida)
- [Tecnologias](#tecnologias)

---

## Arquitetura

```
FastAPI (Python 3.11)
├── backend/
│   ├── core/          → Modelos, banco, segurança (JWT, Fernet, bcrypt)
│   ├── auth/          → Registro, login, SSO, perfis RBAC
│   ├── financeiro/    → Contas, categorias, dívidas, recorrências, relatórios
│   ├── combustivel/   → Abastecimentos e cálculo de consumo
│   ├── mercado/       → Compras de supermercado com itens
│   ├── credenciais/   → Cofre de senhas criptografadas
│   ├── assistente/    → Bot único de WhatsApp (Goku): finanças multi-LLM + tool-calling de agendamento
│   └── agendamento/   → Sub-recursos de agendamento (horários/serviços/clientes/Google Calendar) — sem webhook próprio
├── frontend/
│   ├── financeiro/    → Dashboard financeiro, contas, combustível, mercado
│   ├── credenciais/   → Cofre de senhas
│   └── assistente/    → Painel único do Goku, com abas (WhatsApp/IA/Agenda/Horários/Serviços/Clientes/Personalidade)
├── seed.py            → Inicialização do banco (perfis + admin)
├── Dockerfile
└── requirements.txt
```

**Banco de dados:** PostgreSQL via SQLAlchemy  
**Autenticação:** JWT (HS256, 24h) com controle de acesso por perfis (RBAC)  
**Frontend:** HTML5 + TailwindCSS + Chart.js, servido como arquivos estáticos pelo FastAPI

---

## Módulos

### 1. Portal Administrativo

Ponto de entrada do sistema. Gerencia usuários, autenticação e atribuição de perfis de acesso.

> **Todos os outros módulos dependem do Portal.** O cadastro de usuários e a atribuição de perfis acontecem exclusivamente aqui.

**O que faz:**
- Registro de usuários (e-mail + senha)
- Login com JWT (válido por 24h)
- SSO para módulos internos
- Atribuição de perfis RBAC: `dashboard`, `senhas`, `abastecimento`, `financeiro`, `credenciais`, `games`
- Criação automática do perfil "Meu Perfil" no cadastro
- Redirecionamento pós-login baseado nos perfis do usuário

**Rotas:** `/auth/register`, `/auth/login`, `/auth/sso`, `/me/perfis`  
**Código:** `backend/auth/`  
**Frontend:** `frontend/financeiro/index.html` (tela de login)

---

### 2. Automação Financeira

Gestão financeira completa com contas, categorias, recorrências automáticas e relatórios.

**Perfil necessário:** `dashboard`

**O que faz:**
- CRUD de contas/despesas com parcelamento automático (divide em N parcelas)
- Categorias de despesa personalizadas por usuário
- Dívidas de terceiros com status de pagamento
- Motor de recorrência mensal — clona contas vitalícias e parceladas para o mês seguinte
- Dashboard com KPIs (receitas, despesas, saldo) e gráficos (pizza por categoria, barras receita vs despesa)
- Exportação para Excel (.xlsx) e PDF
- Filtro por competência (mês/ano)

**Como funciona o parcelamento:**
1. Usuário cria conta com `tipo_recorrencia = "parcelada"` e `total_parcelas = 6`
2. Sistema gera 6 registros, cada um com vencimento +1 mês e parcela numerada (1/6, 2/6...)

**Como funciona a recorrência:**
1. `POST /recorrencias/processar/?mes=6&ano=2026`
2. Busca contas do mês onde `mes_seguinte_processado = 0`
3. Clona para o mês seguinte, marca original como processada

**Recebe lançamentos automáticos de:** Combustível, Assistente Virtual, Mercado

**Rotas:** `/contas/`, `/categorias/`, `/dividas/`, `/recorrencias/processar/`, `/relatorios/excel/contas`, `/relatorios/pdf/contas`  
**Código:** `backend/financeiro/`  
**Frontend:** `frontend/financeiro/` (dashboard.html, contas.html)

---

### 3. Assistente Virtual (Goku)

Bot único de WhatsApp (Meta Cloud API) que cobre finanças pessoais **e** agendamento de serviços na mesma conversa. Historicamente eram dois módulos separados (Agendamento Inteligente via Meta; Assistente/Goku, que passou por uma fase self-hosted via Evolution API/Baileys entre 06/2026 e 07/2026) — foram fundidos: a arquitetura de tool-calling do agendamento foi generalizada para cobrir também as ações financeiras, e o canal WhatsApp voltou a ser a Meta Cloud API.

**O que faz:**
- Usa LLM (Gemini → Groq → Ollama, por prioridade com fallback) pra entender a mensagem — credenciais únicas em `AssistenteConfig.provedores_llm` (cifradas com Fernet)
- **Tool-calling opcional** (`usar_tool_calling`, por config) — quando ligado, o LLM chama diretamente uma tool em vez de passar por classificação manual de intenção:
  - `registrar_gasto`, `consultar_financas` — ações financeiras
  - `buscar_horarios_disponiveis`, `pre_reservar_horario`, `confirmar_agendamento`, `cancelar_agendamento`, `reagendar_agendamento` — ações de agendamento (só oferecidas se `AgendamentoConfig.ativo=True`)
- **Fluxo legado** (flag desligada, padrão) — `detectar_intencao()` classifica em `financeiro_registro`/`financeiro_consulta`/`chat` e roteia manualmente em Python
- **OCR de notas fiscais e loop de campo faltante** (`RegistroPendente`) ficam **fora** do tool-calling em ambos os casos — são máquinas de estado determinísticas, sempre ativas
- **Registro automático** — cria lançamentos no módulo Financeiro; se for mercado (foto ou texto), cria em Mercado em vez de uma conta genérica
- **Agendamento** — cadastro de serviços/horários, clientes identificados pelo `numero_autorizado` (bot é pessoal, sem clientes externos), sincronização com Google Calendar
- **Personalidade configurável** — nome do assistente, tom de voz, personalidade, instruções extras
- **Segurança** — webhook autenticado por assinatura HMAC SHA-256 (`X-Hub-Signature-256`, validada contra `WHATSAPP_APP_SECRET`) e handshake de verificação da Meta (`hub.challenge`), só processa mensagens do número autorizado

**Ciclo de vida do agendamento:**
```
pre_reservado (5 min TTL) → confirmado → concluido
                                       → cancelado
```

**Fluxo de nota fiscal:**
```
Foto no WhatsApp → Download da imagem → Gemini Vision (OCR)
→ JSON {estabelecimento, itens[], valor_total, forma_pagamento}
→ Se supermercado: CompraSupermercado + ItemCompra[]
→ Cria Conta no Financeiro
→ Responde: "Nota registrada! Mercado X | R$ 150,50"
```

**Tarefas agendadas (cron):**
| Tarefa | Intervalo | Descrição |
|--------|-----------|-----------|
| Limpar pré-reservas expiradas | 1 min | Remove agendamentos não confirmados |
| Enviar lembretes | 30 min | WhatsApp de lembrete via Meta Cloud API |
| Sincronizar Google Calendar | 15 min | Busca alterações externas |
| Renovar canais push | 12h | Renova push notifications do Google |

**WhatsApp:** Meta WhatsApp Cloud API — token de acesso + Phone Number ID por usuário, canal único do sistema  
**Configurações:** nome_assistente, personalidade, tom_voz, instrucoes_extras, numero_autorizado, usar_tool_calling  
**Rotas do bot:** `/assistente/config`, `/assistente/validar`, `/assistente/webhook` (`GET` para o handshake de verificação da Meta — `hub.challenge`; `POST` para receber mensagens, autenticado por assinatura HMAC via `WHATSAPP_APP_SECRET`), `/assistente/simulador/*`  
**Rotas de agendamento (sub-recursos, sem webhook próprio):** `/agendamento/config`, `/agendamento/horarios`, `/agendamento/servicos`, `/agendamento/clients`, `/agendamento/appointments`, `/agendamento/stats`, `/agendamento/google/*`  
**Código:** `backend/assistente/` (routers, llm_gateway.py, adapters/, tools_agendamento.py, tools_financeiro.py, finance_actions.py, gemini.py, whatsapp.py — envio/download de mídia via Graph API) + `backend/agendamento/` (routers de sub-recursos, slots.py, google_sync.py, crypto.py, cron.py) + `backend/core/webhook_security.py` (middleware HMAC)  
**Frontend:** `frontend/assistente/` (index.html — painel único com abas WhatsApp/IA/E-mail-Agenda/Horários/Serviços/Clientes/Personalidade; dashboard.html; console.html)

---

### 4. Gerenciador de Credenciais

Cofre digital para armazenar senhas e dados pessoais com criptografia Fernet.

**Perfil necessário:** `senhas`

**O que faz:**
- Armazena credenciais (sistema, usuário, senha) criptografadas com Fernet
- Organiza por perfis/pessoas (ex: "Pessoal", "Trabalho", "Cônjuge")
- Dados pessoais dinâmicos (chave-valor) por perfil — CPF, telefone, etc.
- Busca e filtro por sistema ou usuário
- Toggle mostrar/ocultar senhas
- Copiar para área de transferência
- Exportação CSV (senhas permanecem criptografadas)

**Segurança:**
- Criptografia Fernet (simétrica) para senhas em repouso
- Descriptografia apenas no momento da consulta pelo usuário autenticado
- Proteção XSS com `escapeHTML()` no frontend

**Rotas:** `/me/senhas/*`, `/pessoas/`, `/exportar-csv`  
**Código:** `backend/credenciais/`  
**Frontend:** `frontend/credenciais/` (index.html, dashboard.html)

---

### 5. Classificador de E-mails

Sistema de triagem e classificação automática de e-mails usando Machine Learning, com extração via IMAP e interface de inbox completa.

> **Repositório separado:** Este módulo roda como serviço independente em `email_classifier/`, com seu próprio banco, Dockerfile e frontend. Integra com o Portal via SSO.

**Perfil necessário:** `emails`

**O que faz:**
- Conecta a contas de e-mail via IMAP (Gmail, Outlook, outros) com senha criptografada
- Extrai e-mails não lidos em lotes de 50, com deduplicação por Message-ID
- Classifica automaticamente usando ML (TF-IDF + Logistic Regression):
  - **Subcategoria** — 11 classes (Compra VT Admissão, Compra VT Extra, Gestão de saldo, Boleto, NF, etc.)
  - **Categoria** — derivada da subcategoria (VT, VR, Outros)
  - **SLA** — prioridade (D+0 urgente, D+1, D+2, D+3+)
  - **Gerencial** — flag para e-mails que precisam de atenção da gestão
- Classificação manual para correção e para alimentar o modelo
- Dashboard com filtros (categoria, subcategoria, SLA, status, conta), busca, paginação
- Jobs assíncronos com barra de progresso em tempo real
- Teste de conexão IMAP antes de salvar conta
- Exportação do dataset em JSON
- SSO integrado com o Portal

**Pipeline de ML:**
- Pré-processamento: lowercase, remoção de HTML/URLs/stopwords (NLTK)
- TF-IDF (unigrams + bigrams, max 10k features) + Logistic Regression (balanced)
- Confiança >= 40% → classificado automaticamente
- Confiança < 40% → status "não classificado", requer revisão manual
- Mínimo 5 amostras por classe para treinamento

**Status do e-mail:** `novo` → `classificado` / `nao_classificado` → `tratado` / `ignorado`

**Rotas:** `/auth/login`, `/auth/sso`, `/api/contas`, `/api/extrair`, `/api/classificar`, `/api/emails`, `/api/treinar`, `/api/exportar-dataset`  
**Código:** `email_classifier/backend/emails/` (extractor.py, trainer.py, routers/)  
**Frontend:** `email_classifier/frontend/` (dashboard.html, contas.html)

---

### 6. Controle de Combustível

Registro de abastecimentos com cálculos automáticos de consumo e integração financeira.

**Perfil necessário:** `abastecimento`

**O que faz:**
- Registra abastecimento: data, combustível (gasolina/etanol), km, litros, valor, forma de pagamento
- **Cálculos automáticos:**
  - Distância percorrida = km_atual − km_anterior
  - Média de consumo = distância / litros (quando tanque cheio)
  - Sugestão de preço baseada no último abastecimento
- **Calculadora Flex** — compara qual combustível compensa mais usando preços atuais + médias históricas
- **Integração financeira** — pagamentos à vista (PIX, débito, dinheiro) criam automaticamente um lançamento no módulo Financeiro com categoria "Combustível"
- Estatísticas com mediana de consumo por tipo de combustível
- Recálculo retroativo de todas as médias

**Rotas:** `/abastecimentos/`, `/abastecimentos/recalcular`  
**Código:** `backend/combustivel/`  
**Frontend:** `frontend/financeiro/combustivel.html`

---

### 7. Controle de Mercado

Registro de compras de supermercado com itens detalhados.

**Perfil necessário:** `financeiro`

**O que faz:**
- Registra compras com data, loja, forma de pagamento e bandeira do vale
- Itens detalhados com nome, valor e categoria
- Totais por forma de pagamento (débito, crédito, vale alimentação)
- Integração com Assistente Virtual (Goku) — itens populados via OCR de nota fiscal

**Rotas:** `/mercado/compras`  
**Código:** `backend/mercado/`  
**Frontend:** `frontend/financeiro/mercado.html`

---

## Integrações entre Módulos

```
Portal Administrativo (cadastro + perfis RBAC)
    │
    │ JWT Token
    ▼
┌─────────────────┐    lançamento     ┌─────────────────────┐
│   Combustível    │ ───automático───► │ Automação Financeira │
└─────────────────┘                   └─────────┬───────────┘
                                                ▲
┌─────────────────┐   gasto por texto           │
│   Assistente    │ ───ou nota fiscal──────────►│
│   Virtual       │                              │
│   (Goku) —      │ ──nota de mercado──────────►│ Controle de Mercado
│   finanças +    │
│   agendamento   │   (futuro: faturamento) ────┘
└─────────────────┘

┌─────────────────┐
│   Gerenciador   │   (independente)
│   de Credenciais│
└─────────────────┘

┌─────────────────┐
│  Classificador  │   (serviço separado, SSO com Portal)
│   de E-mails    │
└─────────────────┘
```

---

## Instalação e Execução

### Pré-requisitos

- Python 3.11+
- PostgreSQL
- Node.js (opcional, apenas para desenvolvimento frontend)

### Setup local

```bash
# 1. Clonar o repositório
git clone <url-do-repo>
cd central_backend

# 2. Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 3. Instalar dependências
pip install -r requirements.txt

# 4. Configurar variáveis de ambiente
cp .env.example .env
# Editar o .env com suas credenciais (ver seção abaixo)

# 5. Inicializar o banco (cria tabelas, perfis e usuário admin)
python seed.py

# 6. Rodar o servidor
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker

```bash
docker build -t central-sistemas .
docker run -p 8000:8000 --env-file .env central-sistemas
```

### Acessando os módulos

| Módulo | URL |
|--------|-----|
| Login | `http://localhost:8000/financeiro/` |
| Dashboard Financeiro | `http://localhost:8000/financeiro/dashboard.html` |
| Contas | `http://localhost:8000/financeiro/contas.html` |
| Combustível | `http://localhost:8000/financeiro/combustivel.html` |
| Mercado | `http://localhost:8000/financeiro/mercado.html` |
| Credenciais | `http://localhost:8000/credenciais/` |
| Assistente (dashboard) | `http://localhost:8000/assistente-painel/dashboard.html` |
| Assistente (config, com abas) | `http://localhost:8000/assistente-painel/` |
| Assistente (console) | `http://localhost:8000/assistente-painel/console.html` |

### Usuário admin padrão

O `seed.py` cria automaticamente:
- **E-mail:** `almeidainteligencia@gmail.com` (ou `ADMIN_EMAIL`)
- **Senha:** `REDACTED` (ou `ADMIN_SENHA`)
- **Perfis:** todos os perfis atribuídos

---

## Variáveis de Ambiente

| Variável | Obrigatória | Descrição |
|----------|:-----------:|-----------|
| `DATABASE_URL` | Sim | URL de conexão PostgreSQL |
| `JWT_SECRET_KEY` | Sim | Chave secreta para tokens JWT |
| `FERNET_SECRET_KEY` | Sim | Chave de criptografia Fernet (senhas) |
| `PORTAL_SECRET_KEY` | Não | Chave para validação SSO |
| `ADMIN_EMAIL` | Não | E-mail do admin (default: almeidainteligencia@gmail.com) |
| `ADMIN_SENHA` | Não | Senha do admin (default: REDACTED) |
| `ALLOWED_ORIGINS` | Não | Origens CORS permitidas |
| `GOOGLE_CLIENT_ID` | Não* | Client ID Google OAuth (agendamento) |
| `GOOGLE_CLIENT_SECRET` | Não* | Client Secret Google OAuth (agendamento) |
| `APP_BASE_URL` | Não* | URL base da aplicação (agendamento) |
| `TESTING` | Não | Se definida, desativa o scheduler |

> \* Necessárias apenas se usar integração com Google Calendar no módulo de Agendamento.
>
> As chaves de API dos LLMs (Gemini, Groq) e tokens do WhatsApp são configuradas **por usuário** nos painéis de cada módulo, não em variáveis de ambiente.

---

## Estrutura do Projeto

```
central_backend/
├── backend/
│   ├── core/
│   │   ├── models.py          # Todos os modelos SQLAlchemy
│   │   ├── schemas.py         # Todos os schemas Pydantic
│   │   ├── database.py        # Engine + SessionLocal
│   │   └── security.py        # JWT, bcrypt, Fernet, require_perfil
│   │
│   ├── auth/
│   │   └── routers/
│   │       ├── auth.py        # POST /auth/register, /auth/login, /auth/sso
│   │       └── perfis.py      # GET /me/perfis
│   │
│   ├── financeiro/
│   │   └── routers/
│   │       ├── contas.py      # CRUD /contas/
│   │       ├── categorias.py  # CRUD /categorias/
│   │       ├── dividas.py     # CRUD /dividas/
│   │       ├── recorrencias.py # POST /recorrencias/processar/
│   │       └── relatorios.py  # GET /relatorios/excel|pdf/contas
│   │
│   ├── combustivel/
│   │   └── routers/
│   │       └── abastecimentos.py  # CRUD /abastecimentos/
│   │
│   ├── mercado/
│   │   └── routers/
│   │       └── compras.py     # CRUD /mercado/compras
│   │
│   ├── credenciais/
│   │   └── routers/
│   │       ├── senhas.py      # CRUD /me/senhas/
│   │       ├── pessoas.py     # CRUD /pessoas/
│   │       └── csv.py         # GET /exportar-csv
│   │
│   ├── assistente/             # Bot único de WhatsApp (finanças + agendamento)
│   │   ├── routers/
│   │   │   ├── config.py      # CRUD /assistente/config (cifra provedores_llm)
│   │   │   ├── webhook.py     # Webhook único — imagem / RegistroPendente / tool-calling / legado
│   │   │   └── simulador.py   # Console de simulação
│   │   ├── llm_gateway.py     # Orquestrador único de tool-calling (financeiro + agendamento)
│   │   ├── adapters/          # Gemini/Groq/Ollama com function-calling nativo
│   │   │   ├── base.py        # LlmResponse, ToolCall, AGENDAMENTO_TOOLS_SCHEMA, FINANCEIRO_TOOLS_SCHEMA
│   │   │   ├── gemini_adapter.py
│   │   │   ├── groq_adapter.py
│   │   │   └── ollama_adapter.py
│   │   ├── tools_agendamento.py # Execução das 5 tools de agendamento contra o banco
│   │   ├── tools_financeiro.py  # Execução das tools financeiras (registrar_gasto, consultar_financas)
│   │   ├── finance_actions.py   # Lógica pura financeira (reusada pelo fluxo legado e pelas tools)
│   │   ├── gemini.py           # Motor sem tool-calling: chat livre, detecção de intenção, OCR (fluxo legado)
│   │   └── whatsapp.py         # Envio de mensagens + download de mídia (Meta Graph API)
│   │
│   ├── agendamento/             # Sub-recursos de agendamento — SEM webhook próprio
│   │   ├── routers/
│   │   │   ├── config.py      # Config de negócio (catálogo, mensagens, Google Calendar)
│   │   │   ├── horarios.py    # Horários de funcionamento
│   │   │   ├── servicos.py    # CRUD de serviços
│   │   │   ├── clients.py     # Lista de clientes
│   │   │   ├── appointments.py # Agendamentos + slots disponíveis
│   │   │   ├── dashboard_stats.py # KPIs
│   │   │   └── google_calendar.py # OAuth + sync Google
│   │   ├── google_sync.py     # Sincronização Google Calendar
│   │   ├── slots.py           # Cálculo de horários disponíveis
│   │   ├── cron.py            # Tarefas agendadas (APScheduler) — lembretes via Meta Cloud API
│   │   └── crypto.py          # Criptografia Fernet (reusada por assistente/config.py)
│   │
│   └── main.py                # App FastAPI + registro de routers + scheduler
│
├── frontend/
│   ├── shared/                 # sidebar.js + sidebar.css — menu lateral e breadcrumb
│   │                           # compartilhados por financeiro/assistente/credenciais
│   │                           # (servido via mount /shared no main.py). email_classifier/
│   │                           # NÃO usa esse componente — é uma base de código à parte.
│   ├── financeiro/            # Dashboard, contas, combustível, mercado
│   ├── credenciais/            # Cofre de senhas
│   └── assistente/             # Painel único (index.html com abas, dashboard.html, console.html)
│
├── tests/                     # Testes automatizados
├── seed.py                    # Inicialização do banco
├── Dockerfile
├── requirements.txt
└── README.md

# Serviço separado (mesmo repositório pai):
email_classifier/
├── backend/
│   ├── core/                  # Database, models (User), security (JWT)
│   └── emails/
│       ├── extractor.py       # IMAP: contar, extrair lotes, marcar processados
│       ├── trainer.py         # ML: treinar (TF-IDF + LogReg), classificar
│       ├── models.py          # ContaEmail, EmailExtraido
│       └── routers/
│           ├── auth.py        # Login, SSO
│           └── emails.py      # CRUD e-mails, contas, jobs, treino
├── frontend/
│   ├── index.html             # Login
│   ├── dashboard.html/js      # Inbox com filtros, modais, progresso
│   └── contas.html            # Configuração de contas IMAP
├── Dockerfile
└── requirements.txt
```

---

## API — Referência Rápida

### Autenticação
| Método | Rota | Auth | Descrição |
|--------|------|:----:|-----------|
| `POST` | `/auth/register` | — | Cadastrar usuário |
| `POST` | `/auth/login` | — | Login (retorna JWT) |
| `POST` | `/auth/sso` | — | Single Sign-On |
| `GET` | `/me/perfis` | JWT | Listar perfis do usuário |

### Financeiro (perfil: `dashboard`)
| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/contas/` | Criar conta (suporta parcelamento) |
| `GET` | `/contas/?mes=X&ano=Y` | Listar contas do mês |
| `PUT` | `/contas/{id}` | Atualizar conta |
| `DELETE` | `/contas/{id}` | Excluir conta |
| `POST/GET` | `/categorias/` | Criar / listar categorias |
| `DELETE` | `/categorias/{id}` | Excluir categoria |
| `POST/GET` | `/dividas/` | Criar / listar dívidas |
| `PUT/DELETE` | `/dividas/{id}` | Atualizar / excluir dívida |
| `POST` | `/recorrencias/processar/` | Processar recorrências do mês |
| `GET` | `/relatorios/excel/contas` | Exportar Excel |
| `GET` | `/relatorios/pdf/contas` | Exportar PDF |

### Combustível (perfil: `abastecimento`)
| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/abastecimentos/` | Registrar abastecimento |
| `GET` | `/abastecimentos/?mes=X&ano=Y` | Listar com estatísticas |
| `POST` | `/abastecimentos/recalcular` | Recalcular médias |
| `DELETE` | `/abastecimentos/{id}` | Excluir |

### Mercado (perfil: `financeiro`)
| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/mercado/compras` | Criar compra com itens |
| `GET` | `/mercado/compras?mes=X&ano=Y` | Listar compras |
| `DELETE` | `/mercado/compras/{id}` | Excluir compra |

### Credenciais (perfil: `senhas`)
| Método | Rota | Descrição |
|--------|------|-----------|
| `GET/POST` | `/me/senhas/perfil/` | Listar / criar perfis |
| `GET` | `/me/senhas/{pessoa_id}` | Listar senhas (descriptografadas) |
| `POST` | `/me/senhas/` | Salvar senha (criptografa) |
| `DELETE` | `/me/senhas/credencial/{id}` | Excluir senha |
| `GET/POST` | `/me/senhas/propriedades/{pessoa_id}` | Dados pessoais |
| `POST/DELETE` | `/me/senhas/dados/` | Adicionar / excluir dado |
| `POST/GET` | `/pessoas/` | Criar / listar pessoas |
| `POST` | `/pessoas/{id}/principal` | Definir pessoa principal |
| `GET` | `/exportar-csv` | Exportar CSV |

### Classificador de E-mails (serviço separado — perfil: `emails`)
| Método | Rota | Auth | Descrição |
|--------|------|:----:|-----------|
| `POST` | `/auth/login` | — | Login |
| `POST` | `/auth/sso` | — | SSO via Portal |
| `GET/POST/PUT/DELETE` | `/api/contas` | JWT | CRUD de contas IMAP |
| `POST` | `/api/contas/{id}/testar` | JWT | Testar conexão IMAP |
| `POST` | `/api/extrair` | JWT | Extrair e-mails (job async) |
| `POST` | `/api/classificar` | JWT | Classificar e-mails (job async) |
| `GET` | `/api/job/{id}` | JWT | Progresso do job |
| `GET` | `/api/emails` | JWT | Listar e-mails (filtros + paginação) |
| `PUT` | `/api/emails/{id}` | JWT | Atualizar classificação |
| `POST` | `/api/treinar` | JWT | Treinar modelo ML |
| `GET` | `/api/exportar-dataset` | JWT | Exportar JSON |

### Assistente Virtual
| Método | Rota | Auth | Descrição |
|--------|------|:----:|-----------|
| `POST` | `/assistente/validar` | JWT | Validar credenciais |
| `GET/POST/PUT` | `/assistente/config` | JWT | Configuração (chaves sensíveis mascaradas no GET) |
| `GET` | `/assistente/webhook` | `hub.verify_token` (query) | Handshake de verificação da Meta ao cadastrar a Callback URL |
| `POST` | `/assistente/webhook` | Assinatura HMAC (`X-Hub-Signature-256`) | Webhook único — Meta WhatsApp Cloud API, cobre finanças e agendamento |
| `POST` | `/assistente/simulador/chat` | JWT | Simular mensagem (console) |
| `DELETE` | `/assistente/simulador/historico` | JWT | Limpar histórico do simulador |

Sub-recursos de agendamento (mesmo bot, sem webhook próprio):
| Método | Rota | Auth | Descrição |
|--------|------|:----:|-----------|
| `GET/POST/PUT` | `/agendamento/config` | JWT | Config de negócio (catálogo, mensagens, Google Calendar) |
| `GET/POST` | `/agendamento/horarios` | JWT | Horários |
| `GET/POST/PUT/DELETE` | `/agendamento/servicos` | JWT | Serviços |
| `GET` | `/agendamento/clients` | JWT | Clientes |
| `GET` | `/agendamento/appointments` | JWT | Agendamentos |
| `GET` | `/agendamento/appointments/slots` | JWT | Slots disponíveis |
| `PUT` | `/agendamento/appointments/{id}/status` | JWT | Alterar status |
| `GET` | `/agendamento/stats` | JWT | KPIs |
| `GET` | `/agendamento/google/auth-url` | JWT | URL OAuth Google |
| `GET` | `/agendamento/google/callback` | — | Callback OAuth |
| `POST` | `/agendamento/google/disconnect` | JWT | Desconectar Google |

---

## Tecnologias

| Componente | Tecnologia |
|------------|-----------|
| Backend | FastAPI 0.115 + Uvicorn |
| ORM | SQLAlchemy 2.0 |
| Banco de dados | PostgreSQL (psycopg2) |
| Autenticação | JWT (python-jose) + bcrypt |
| Criptografia | Fernet (cryptography) |
| Frontend | HTML5 + TailwindCSS + Chart.js |
| IA / LLM | Google Gemini 2.0 Flash, Groq LLaMA 3.3 70B, Ollama |
| WhatsApp | Meta WhatsApp Cloud API — canal único |
| Calendário | Google Calendar API v3 (google-auth + google-auth-oauthlib) |
| HTTP Client | httpx |
| Relatórios | openpyxl (Excel) + ReportLab (PDF) |
| Scheduler | APScheduler 3.10 |
| ML / NLP | scikit-learn 1.5 (TF-IDF + LogReg), NLTK 3.9 (stopwords), joblib |
| Validação | Pydantic 2.9 |
| Deploy | Docker |
| Python | 3.11 |

---

## Documentação Completa

Para documentação detalhada de cada módulo com modelos de dados, lógica de negócio, instruções para alterações e diagramas de integração, consulte o arquivo **[DOCUMENTACAO_MODULOS.md](../DOCUMENTACAO_MODULOS.md)**.
