# Documento de Requisitos — Almeida Inteligência

**Versão:** 1.0  
**Data:** Junho 2026  
**Projeto:** Portal Corporativo Almeida Inteligência  

---

## 1. Visão Geral

O Portal Almeida Inteligência é um sistema interno modular que centraliza ferramentas de produtividade, automação e gestão para uso corporativo. O sistema é composto por um portal de autenticação único (SSO) e módulos independentes acessíveis conforme o perfil do usuário.

---

## 2. Requisitos Funcionais

### 2.1 Portal de Autenticação (RF-AUTH)

| ID | Requisito |
|----|-----------|
| RF-AUTH-01 | O sistema deve permitir login com e-mail e senha |
| RF-AUTH-02 | O sistema deve gerar token JWT com expiração de 8 horas |
| RF-AUTH-03 | O sistema deve exibir apenas os módulos autorizados para o perfil do usuário após login |
| RF-AUTH-04 | O sistema deve realizar logout automático após 30 minutos de inatividade |
| RF-AUTH-05 | O sistema deve exibir aviso de expiração de sessão com 60 segundos de antecedência |
| RF-AUTH-06 | O sistema deve redirecionar para login com mensagem ao expirar o token |
| RF-AUTH-07 | O sistema deve revalidar o token ao retornar de aba inativa (visibilitychange) |

### 2.2 Painel Administrativo (RF-ADMIN)

| ID | Requisito |
|----|-----------|
| RF-ADMIN-01 | O administrador deve poder criar, editar e desativar usuários |
| RF-ADMIN-02 | O administrador deve poder criar e gerenciar perfis de acesso |
| RF-ADMIN-03 | O administrador deve poder associar sistemas (módulos) a perfis |
| RF-ADMIN-04 | O administrador deve poder cadastrar novos sistemas/módulos com URL, ícone e slug |
| RF-ADMIN-05 | O sistema deve impedir exclusão de perfil que possua usuários vinculados |
| RF-ADMIN-06 | O sistema deve registrar e exibir a quantidade de usuários por perfil |

### 2.3 Classificador de E-mails (RF-EMAIL)

| ID | Requisito |
|----|-----------|
| RF-EMAIL-01 | O sistema deve permitir cadastro de contas de e-mail via protocolo IMAP |
| RF-EMAIL-02 | O sistema deve testar a conexão IMAP antes de salvar a conta |
| RF-EMAIL-03 | O sistema deve extrair e-mails das caixas de entrada de forma assíncrona |
| RF-EMAIL-04 | O sistema deve classificar e-mails automaticamente usando modelo ML (TF-IDF + Logistic Regression) |
| RF-EMAIL-05 | O sistema deve permitir retreinamento do modelo com os dados existentes |
| RF-EMAIL-06 | O sistema deve exibir status e progresso dos jobs de extração e classificação |
| RF-EMAIL-07 | O sistema deve permitir listagem de e-mails com filtros por categoria, subcategoria, SLA, status e conta |
| RF-EMAIL-08 | O sistema deve suportar paginação na listagem de e-mails |
| RF-EMAIL-09 | O sistema deve permitir edição manual de categoria, subcategoria, SLA e status de e-mails |
| RF-EMAIL-10 | O sistema deve exportar o dataset de e-mails em formato JSON |
| RF-EMAIL-11 | O sistema deve exibir a quantidade de e-mails pendentes de classificação |
| RF-EMAIL-12 | As senhas das contas IMAP devem ser armazenadas criptografadas com Fernet |
| RF-EMAIL-13 | O sistema deve permitir ativar/desativar contas de e-mail individualmente |

### 2.4 Gerenciador de Credenciais (RF-CRED)

| ID | Requisito |
|----|-----------|
| RF-CRED-01 | O sistema deve permitir criação de múltiplos perfis (personas) por usuário |
| RF-CRED-02 | O sistema deve permitir definir um perfil como principal |
| RF-CRED-03 | O sistema deve armazenar credenciais (sistema, usuário, senha) criptografadas com Fernet |
| RF-CRED-04 | O sistema deve descriptografar e exibir senhas apenas quando solicitado pelo usuário autenticado |
| RF-CRED-05 | O sistema deve permitir copiar a senha para o clipboard sem exibi-la na tela |
| RF-CRED-06 | O sistema deve permitir exclusão de credenciais individuais |
| RF-CRED-07 | O sistema deve permitir adicionar dados pessoais dinâmicos (chave-valor) a cada perfil |
| RF-CRED-08 | O sistema deve exportar as credenciais em CSV sem incluir as senhas |
| RF-CRED-09 | O acesso às credenciais deve ser restrito ao usuário dono do perfil |

### 2.5 Automação Financeira (RF-FIN)

| ID | Requisito |
|----|-----------|
| RF-FIN-01 | O sistema deve permitir cadastro de contas/lançamentos financeiros com descrição, valor, vencimento, natureza (receita/despesa) e status |
| RF-FIN-02 | O sistema deve suportar lançamentos parcelados com geração automática das parcelas |
| RF-FIN-03 | O sistema deve suportar lançamentos recorrentes (mensais/vitalícios) |
| RF-FIN-04 | O sistema deve filtrar lançamentos por mês e ano |
| RF-FIN-05 | O sistema deve exibir KPIs: total de receitas, despesas, saldo e a pagar no período |
| RF-FIN-06 | O sistema deve permitir marcar lançamentos como pagos |
| RF-FIN-07 | O sistema deve permitir criação e gerenciamento de categorias de despesa |
| RF-FIN-08 | O sistema deve permitir registro de dívidas de terceiros com devedor, valor e vencimento |
| RF-FIN-09 | O sistema deve exportar lançamentos em formato Excel (.xlsx) |
| RF-FIN-10 | O sistema deve exportar lançamentos em formato PDF |
| RF-FIN-11 | O acesso aos dados financeiros deve ser restrito ao usuário dono dos lançamentos |

### 2.6 Controle de Combustível (RF-COMB)

| ID | Requisito |
|----|-----------|
| RF-COMB-01 | O sistema deve registrar abastecimentos com data, tipo de combustível, KM atual, litros, valor unitário e valor total |
| RF-COMB-02 | O sistema deve calcular automaticamente a distância percorrida desde o último abastecimento |
| RF-COMB-03 | O sistema deve calcular automaticamente a média de consumo (km/l) quando o tanque for completo |
| RF-COMB-04 | O sistema deve manter histórico de médias e exibir mediana de consumo por tipo de combustível |
| RF-COMB-05 | O sistema deve registrar automaticamente o abastecimento como lançamento financeiro quando o pagamento for à vista (pix, débito ou dinheiro) |
| RF-COMB-06 | O sistema deve filtrar histórico de abastecimentos por mês e ano |
| RF-COMB-07 | O sistema deve permitir exclusão de registros de abastecimento |

---

## 3. Requisitos Não-Funcionais

### 3.1 Segurança (RNF-SEG)

| ID | Requisito |
|----|-----------|
| RNF-SEG-01 | Senhas de usuários devem ser armazenadas com hash bcrypt (cost factor 12) |
| RNF-SEG-02 | Senhas de sistemas e credenciais IMAP devem ser criptografadas com Fernet (AES-128-CBC) |
| RNF-SEG-03 | Tokens JWT devem ter expiração máxima de 8 horas |
| RNF-SEG-04 | Chaves secretas (JWT, Fernet) não devem ser commitadas no repositório |
| RNF-SEG-05 | O CSV de exportação de credenciais não deve conter senhas |
| RNF-SEG-06 | Todos os endpoints protegidos devem retornar HTTP 401 para tokens inválidos/expirados |
| RNF-SEG-07 | Dados de um usuário não devem ser acessíveis por outro usuário autenticado |

### 3.2 Desempenho (RNF-DESEMP)

| ID | Requisito |
|----|-----------|
| RNF-DESEMP-01 | A extração e classificação de e-mails deve ser executada de forma assíncrona (jobs) |
| RNF-DESEMP-02 | Relatórios devem ser gerados via streaming para não bloquear a API |
| RNF-DESEMP-03 | O sistema deve suportar múltiplos usuários simultâneos sem degradação |

### 3.3 Manutenibilidade (RNF-MANUT)

| ID | Requisito |
|----|-----------|
| RNF-MANUT-01 | O sistema deve ser organizado em módulos independentes por domínio funcional |
| RNF-MANUT-02 | Cada módulo deve possuir sua própria suite de testes |
| RNF-MANUT-03 | A cobertura de testes deve ser de no mínimo 85% por módulo |
| RNF-MANUT-04 | Variáveis de ambiente devem ser documentadas no docker-compose.yml |

### 3.4 Disponibilidade (RNF-DISP)

| ID | Requisito |
|----|-----------|
| RNF-DISP-01 | Todos os serviços devem ter política `restart: unless-stopped` no Docker |
| RNF-DISP-02 | O banco de dados deve passar por health check antes dos backends iniciarem |

### 3.5 Usabilidade (RNF-UX)

| ID | Requisito |
|----|-----------|
| RNF-UX-01 | A interface deve seguir a identidade visual Almeida Inteligência (dark theme, verde #3DDB82, fonte Inter) |
| RNF-UX-02 | A interface deve ser responsiva para dispositivos móveis |
| RNF-UX-03 | O sistema deve exibir feedback visual (toast) para todas as operações de CRUD |
| RNF-UX-04 | O sistema deve exibir estados de carregamento durante operações assíncronas |

---

## 4. Regras de Negócio

| ID | Regra |
|----|-------|
| RN-01 | Ao registrar um usuário no módulo central, um perfil padrão ("Meu Perfil") é criado automaticamente |
| RN-02 | O primeiro perfil criado por um usuário é automaticamente definido como principal |
| RN-03 | Um perfil de acesso não pode ser excluído se houver usuários vinculados a ele |
| RN-04 | Abastecimentos pagos à vista (pix, débito, dinheiro) geram automaticamente um lançamento financeiro como despesa paga |
| RN-05 | O cálculo de média de consumo (km/l) só é realizado quando o tanque for abastecido completo |
| RN-06 | Lançamentos parcelados geram N registros no banco com vencimentos mensais sequenciais |
| RN-07 | O modelo de classificação de e-mails requer confiança mínima de 40% para classificar automaticamente |
| RN-08 | Credenciais de e-mail (IMAP) são descriptografadas apenas em memória, nunca persistidas em texto plano |

---

## 5. Integrações e Dependências Externas

| Dependência | Uso | Módulo |
|-------------|-----|--------|
| Servidores IMAP (Gmail, Outlook, etc.) | Extração de e-mails | Email Classifier |
| PostgreSQL 15 | Persistência de dados | Todos os backends |
| Docker / Docker Compose | Orquestração de containers | Infraestrutura |

---

## 6. Inventário de Endpoints

**Total:** 96 endpoints HTTP  
**Autenticados:** 84 (87,5%)  
**Públicos:** 4 (login, register, health)

| Módulo | Quantidade |
|--------|-----------|
| Portal Auth/Admin | 18 |
| Central Auth | 3 |
| Credenciais | 10 |
| Financeiro | 13 |
| Combustível | 3 |
| Email Classifier | 49 |
| **Total** | **96** |
