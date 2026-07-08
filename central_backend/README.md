# Central Sistemas — Almeida Inteligência

Plataforma modular para automação de processos pessoais e profissionais: gestão financeira, agendamento inteligente via WhatsApp com IA, assistente virtual, cofre de credenciais e mais.

---

## Sumário

- [Arquitetura](#arquitetura)
- [Módulos](#módulos)
  - [Portal Administrativo](#1-portal-administrativo)
  - [Automação Financeira](#2-automação-financeira)
  - [Agendamento Inteligente](#3-agendamento-inteligente)
  - [Assistente Virtual (Goku)](#4-assistente-virtual-goku)
  - [Gerenciador de Credenciais](#5-gerenciador-de-credenciais)
  - [Classificador de E-mails](#6-classificador-de-e-mails)
  - [Controle de Combustível](#7-controle-de-combustível)
  - [Controle de Mercado](#8-controle-de-mercado)
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
│   ├── assistente/    → Chatbot WhatsApp (Goku) com Gemini/Groq
│   └── agendamento/   → Agendamento via WhatsApp com IA e Google Calendar
├── frontend/
│   ├── financeiro/    → Dashboard financeiro, contas, combustível, mercado
│   ├── credenciais/   → Cofre de senhas
│   ├── assistente/    → Painel de configuração do Goku
│   └── agendamento/   → Painel de agendamento (serviços, horários, clientes)
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

### 3. Agendamento Inteligente

Sistema de agendamento de serviços via WhatsApp com IA conversacional, cálculo de disponibilidade e sincronização com Google Calendar.

**O que faz:**
- Recebe mensagens via WhatsApp Business API
- Usa LLM (Gemini → Groq → Ollama, por prioridade com fallback) para entender o pedido
- LLM pode chamar **tools** para executar ações:
  - `buscar_horarios_disponiveis` — calcula slots livres baseado em horários + serviço + agendamentos existentes
  - `pre_reservar_horario` — bloqueia horário por 5 minutos
  - `confirmar_agendamento` — confirma e sincroniza com Google Calendar
  - `cancelar_agendamento` — cancela e remove do Google Calendar
  - `reagendar_agendamento` — altera data/hora
- Cadastro de serviços (nome, duração, preço)
- Cadastro de horários de funcionamento (dia da semana + faixa horária)
- Clientes identificados automaticamente pelo número de telefone
- Histórico de conversas (sliding window de 6 mensagens)
- Dashboard com KPIs (conversas do dia, agendamentos confirmados, próximos horários)
- Métricas de LLM (provider, tokens, latência, erros)

**Ciclo de vida do agendamento:**
```
pre_reservado (5 min TTL) → confirmado → concluido
                                       → cancelado
```

**Tarefas agendadas (cron):**
| Tarefa | Intervalo | Descrição |
|--------|-----------|-----------|
| Limpar pré-reservas expiradas | 1 min | Remove agendamentos não confirmados |
| Enviar lembretes | 30 min | WhatsApp de lembrete para clientes |
| Sincronizar Google Calendar | 15 min | Busca alterações externas |
| Renovar canais push | 12h | Renova push notifications do Google |

**Rotas:** `/agendamento/config`, `/agendamento/horarios`, `/agendamento/servicos`, `/agendamento/clients`, `/agendamento/appointments`, `/agendamento/stats`, `/agendamento/webhook`, `/agendamento/google/*`  
**Código:** `backend/agendamento/` (routers, llm_gateway, whatsapp, google_sync, slots, cron, adapters/)  
**Frontend:** `frontend/agendamento/` (index, config, horarios, servicos, clientes)

---

### 4. Assistente Virtual (Goku)

Chatbot pessoal via WhatsApp que usa IA para interpretar mensagens, registrar gastos, processar notas fiscais por foto e consultar finanças.

**O que faz:**
- **Detecção de intenção** — classifica a mensagem automaticamente:
  - `financeiro_registro` → registra gasto ("gastei 50 no almoço")
  - `financeiro_consulta` → retorna resumo financeiro do mês
  - `image` → processa foto de nota fiscal via OCR
  - `chat` → conversa livre
- **OCR de notas fiscais** — envia foto → Gemini extrai dados estruturados (estabelecimento, itens, valores, forma de pagamento)
- **Registro automático** — cria lançamentos no módulo Financeiro e compras no módulo Mercado
- **Personalidade configurável** — nome do assistente, tom de voz, personalidade, instruções extras
- **Segurança** — webhook autenticado por `webhook_secret` próprio (query param), e só processa mensagens do número de WhatsApp autorizado
- **Fallback** — se Gemini falhar, tenta Groq automaticamente

**Fluxo de nota fiscal:**
```
Foto no WhatsApp → Download da imagem → Gemini Vision (OCR)
→ JSON {estabelecimento, itens[], valor_total, forma_pagamento}
→ Se supermercado: CompraSupermercado + ItemCompra[]
→ Cria Conta no Financeiro
→ Responde: "Nota registrada! Mercado X | R$ 150,50"
```

**WhatsApp:** Evolution API (Baileys, self-hosted) — conexão por QR Code, sem aprovação da Meta  
**Configurações:** nome_assistente, personalidade, tom_voz, instrucoes_extras, numero_autorizado  
**Rotas:** `/assistente/config`, `/assistente/validar`, `/assistente/qrcode`, `/assistente/connection-state`, `/assistente/webhook` (autenticado por `webhook_secret` na URL, não por JWT)  
**Código:** `backend/assistente/` (routers, gemini.py, whatsapp.py)  
**Frontend:** `frontend/assistente/index.html` (painel de configuração)

---

### 5. Gerenciador de Credenciais

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

### 6. Classificador de E-mails

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

### 7. Controle de Combustível

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

### 8. Controle de Mercado

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
│   (Goku)        │ ──nota de mercado──────────►│ Controle de Mercado
└─────────────────┘                              │
                                                 │
┌─────────────────┐                              │
│   Agendamento   │   (futuro: faturamento) ────┘
│   Inteligente   │
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
| Assistente (config) | `http://localhost:8000/assistente-painel/` |
| Agendamento (config) | `http://localhost:8000/agendamento-painel/` |

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
│   ├── assistente/
│   │   ├── routers/
│   │   │   ├── config.py      # CRUD /assistente/config
│   │   │   └── webhook.py     # Webhook WhatsApp + roteamento por intenção
│   │   ├── gemini.py          # Chat, detecção de intenção, OCR
│   │   └── whatsapp.py        # Envio de mensagens + download de mídia
│   │
│   ├── agendamento/
│   │   ├── routers/
│   │   │   ├── config.py      # Configuração geral
│   │   │   ├── horarios.py    # Horários de funcionamento
│   │   │   ├── servicos.py    # CRUD de serviços
│   │   │   ├── clients.py     # Lista de clientes
│   │   │   ├── appointments.py # Agendamentos + slots disponíveis
│   │   │   ├── dashboard_stats.py # KPIs
│   │   │   ├── webhook.py     # Webhook WhatsApp
│   │   │   └── google_calendar.py # OAuth + sync Google
│   │   ├── llm_gateway.py     # Orquestrador LLM com tool calling
│   │   ├── whatsapp.py        # API WhatsApp
│   │   ├── google_sync.py     # Sincronização Google Calendar
│   │   ├── slots.py           # Cálculo de horários disponíveis
│   │   ├── cron.py            # Tarefas agendadas (APScheduler)
│   │   ├── crypto.py          # Criptografia de chaves de API
│   │   └── adapters/
│   │       ├── base.py        # Interface LlmResponse
│   │       ├── gemini_adapter.py
│   │       ├── groq_adapter.py
│   │       └── ollama_adapter.py
│   │
│   └── main.py                # App FastAPI + registro de routers + scheduler
│
├── frontend/
│   ├── financeiro/            # Dashboard, contas, combustível, mercado
│   ├── credenciais/           # Cofre de senhas
│   ├── assistente/            # Config do Goku
│   └── agendamento/           # Painel de agendamento
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
| `GET` | `/assistente/qrcode` | JWT | Gerar/renovar QR Code de conexão |
| `GET` | `/assistente/connection-state` | JWT | Estado da conexão com o WhatsApp |
| `POST` | `/assistente/webhook?secret=...` | Segredo por URL | Webhook Evolution API (WhatsApp) |

### Agendamento Inteligente
| Método | Rota | Auth | Descrição |
|--------|------|:----:|-----------|
| `GET/POST/PUT` | `/agendamento/config` | JWT | Configuração |
| `POST` | `/agendamento/config/testar-llm` | JWT | Testar LLM |
| `GET/POST` | `/agendamento/horarios` | JWT | Horários |
| `GET/POST/PUT/DELETE` | `/agendamento/servicos` | JWT | Serviços |
| `GET` | `/agendamento/clients` | JWT | Clientes |
| `GET` | `/agendamento/appointments` | JWT | Agendamentos |
| `GET` | `/agendamento/appointments/slots` | JWT | Slots disponíveis |
| `PUT` | `/agendamento/appointments/{id}/status` | JWT | Alterar status |
| `GET` | `/agendamento/stats` | JWT | KPIs |
| `GET/POST` | `/agendamento/webhook` | — | Webhook WhatsApp |
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
| WhatsApp | Meta Cloud API v21.0 (Agendamento) + Evolution API/Baileys self-hosted (Assistente) |
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
