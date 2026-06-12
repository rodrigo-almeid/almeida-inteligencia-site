# Histórias de Usuário — Almeida Inteligência

**Versão:** 1.0  
**Data:** Junho 2026  

---

## Personas

| Persona | Descrição |
|---------|-----------|
| **Administrador** | Responsável pela gestão do portal, usuários e configurações |
| **Usuário Corporativo** | Colaborador com acesso aos módulos autorizados pelo admin |
| **Gestor Financeiro** | Usuário com acesso ao módulo de automação financeira |
| **Analista de E-mails** | Usuário responsável pela triagem e classificação de e-mails |

---

## Épico 1 — Autenticação e Controle de Acesso

### HU-01 — Login no portal
**Como** usuário corporativo  
**Quero** fazer login com meu e-mail e senha  
**Para** acessar os módulos que tenho permissão  

**Critérios de aceite:**
- [ ] Formulário com campos e-mail e senha
- [ ] Exibe mensagem de erro para credenciais inválidas
- [ ] Redireciona para o dashboard após login bem-sucedido
- [ ] Dashboard exibe apenas os módulos autorizados para o meu perfil
- [ ] Token JWT gerado com validade de 8 horas

---

### HU-02 — Logout automático por inatividade
**Como** usuário corporativo  
**Quero** ser desconectado automaticamente após inatividade  
**Para** proteger minha conta quando esqueço o sistema aberto  

**Critérios de aceite:**
- [ ] Após 30 minutos sem interação, exibe aviso com contagem regressiva de 60 segundos
- [ ] O aviso oferece botão "Continuar" para manter a sessão
- [ ] Se não responder, faz logout e redireciona para o login com mensagem explicativa
- [ ] Qualquer interação (clique, digitação, scroll) reinicia o contador

---

### HU-03 — Gestão de usuários (Admin)
**Como** administrador  
**Quero** criar, editar e desativar usuários  
**Para** controlar quem tem acesso ao sistema  

**Critérios de aceite:**
- [ ] Listagem de todos os usuários com nome, e-mail, perfil e status
- [ ] Criação de usuário com nome, e-mail, senha e perfil
- [ ] Edição de qualquer campo do usuário incluindo troca de senha
- [ ] Desativação de usuário sem excluir seu histórico
- [ ] Erro claro ao tentar cadastrar e-mail duplicado

---

### HU-04 — Gestão de perfis de acesso (Admin)
**Como** administrador  
**Quero** criar perfis e associar módulos a eles  
**Para** controlar granularmente o que cada grupo de usuários acessa  

**Critérios de aceite:**
- [ ] Criação de perfil com nome e seleção de sistemas/módulos
- [ ] Edição dos sistemas associados a um perfil existente
- [ ] Exibição da quantidade de usuários em cada perfil
- [ ] Bloqueio de exclusão de perfil com usuários vinculados, com mensagem explicativa

---

### HU-05 — Gestão de módulos/sistemas (Admin)
**Como** administrador  
**Quero** cadastrar e gerenciar os módulos disponíveis no portal  
**Para** adicionar novos sistemas sem precisar alterar o código  

**Critérios de aceite:**
- [ ] Cadastro de sistema com nome, slug, URL, ícone e status ativo/inativo
- [ ] Edição de qualquer atributo de um sistema existente
- [ ] Sistemas inativos não aparecem no dashboard dos usuários
- [ ] Erro claro ao tentar cadastrar slug duplicado

---

## Épico 2 — Classificador de E-mails

### HU-06 — Configurar conta de e-mail IMAP
**Como** analista de e-mails  
**Quero** cadastrar minha conta de e-mail corporativo  
**Para** que o sistema possa acessar e extrair meus e-mails  

**Critérios de aceite:**
- [ ] Formulário com campos: nome, provedor, e-mail, senha, servidor IMAP e porta
- [ ] Botão para testar a conexão antes de salvar
- [ ] Mensagem clara de sucesso ou falha no teste de conexão
- [ ] Senha armazenada criptografada, nunca visível na interface
- [ ] Possibilidade de ativar/desativar a conta sem excluí-la

---

### HU-07 — Extrair e-mails da caixa de entrada
**Como** analista de e-mails  
**Quero** importar e-mails das minhas contas IMAP  
**Para** tê-los disponíveis no sistema para análise  

**Critérios de aceite:**
- [ ] Botão para iniciar extração
- [ ] Extração executada em background (job assíncrono)
- [ ] Barra de progresso ou indicador de andamento
- [ ] Notificação ao concluir com quantidade de e-mails extraídos
- [ ] Mensagem de erro detalhada caso a extração falhe

---

### HU-08 — Classificar e-mails com inteligência artificial
**Como** analista de e-mails  
**Quero** que o sistema classifique automaticamente os e-mails por categoria  
**Para** agilizar a triagem e priorização  

**Critérios de aceite:**
- [ ] Botão para iniciar classificação dos e-mails pendentes
- [ ] Classificação executada em background (job assíncrono)
- [ ] Cada e-mail recebe categoria, subcategoria, flag gerencial e SLA automaticamente
- [ ] Exibição do total de e-mails pendentes antes de classificar
- [ ] Possibilidade de retreinar o modelo com os dados existentes

---

### HU-09 — Consultar e gerenciar e-mails
**Como** analista de e-mails  
**Quero** visualizar e filtrar meus e-mails classificados  
**Para** encontrar rapidamente os que preciso analisar  

**Critérios de aceite:**
- [ ] Listagem paginada de e-mails
- [ ] Filtros por: categoria, subcategoria, SLA, flag gerencial, status e conta de origem
- [ ] Campo de busca por texto
- [ ] Visualização do conteúdo completo do e-mail ao clicar
- [ ] Edição manual de categoria, subcategoria, SLA, flag gerencial e status
- [ ] Exportação do dataset completo em JSON

---

## Épico 3 — Gerenciador de Credenciais

### HU-10 — Organizar credenciais em perfis
**Como** usuário corporativo  
**Quero** criar perfis para organizar minhas senhas  
**Para** separar credenciais pessoais, profissionais e de projetos  

**Critérios de aceite:**
- [ ] Criação de perfil com nome personalizado
- [ ] Listagem de todos os perfis do usuário
- [ ] Possibilidade de definir um perfil como principal
- [ ] O primeiro perfil criado é automaticamente o principal

---

### HU-11 — Armazenar senhas corporativas com segurança
**Como** usuário corporativo  
**Quero** guardar minhas senhas de sistemas no cofre  
**Para** não precisar memorizá-las e ter acesso seguro quando precisar  

**Critérios de aceite:**
- [ ] Cadastro de credencial com sistema, usuário e senha
- [ ] Senha armazenada criptografada (nunca visível no banco de dados)
- [ ] Opção de revelar/ocultar a senha na interface
- [ ] Botão de copiar para clipboard sem exibir a senha na tela
- [ ] Exclusão de credencial com confirmação
- [ ] Acesso restrito: usuário só vê suas próprias credenciais

---

### HU-12 — Exportar lista de sistemas e usuários
**Como** usuário corporativo  
**Quero** exportar minha lista de credenciais em CSV  
**Para** ter um backup dos sistemas e usuários cadastrados  

**Critérios de aceite:**
- [ ] Exportação em formato CSV com colunas: Sistema, Usuário
- [ ] As senhas NÃO devem constar no arquivo exportado
- [ ] Arquivo baixado automaticamente ao clicar no botão

---

### HU-13 — Armazenar dados pessoais dinâmicos
**Como** usuário corporativo  
**Quero** adicionar informações extras (CPF, RG, endereço) a cada perfil  
**Para** centralizar dados importantes de cada persona em um só lugar  

**Critérios de aceite:**
- [ ] Adição de propriedade no formato chave-valor (ex: "CPF" → "123.456.789-00")
- [ ] Listagem de todas as propriedades do perfil
- [ ] Exclusão de propriedade individual
- [ ] Acesso restrito ao dono do perfil

---

## Épico 4 — Automação Financeira

### HU-14 — Registrar lançamentos financeiros
**Como** gestor financeiro  
**Quero** registrar receitas e despesas com vencimento  
**Para** controlar meu fluxo de caixa  

**Critérios de aceite:**
- [ ] Formulário com: descrição, valor, vencimento, natureza (receita/despesa), status e tipo
- [ ] Distinção visual entre receitas (verde) e despesas (vermelho) na listagem
- [ ] Opção de marcar um lançamento como pago diretamente na listagem
- [ ] Exclusão de lançamento com confirmação
- [ ] Acesso restrito: usuário só vê seus próprios lançamentos

---

### HU-15 — Visualizar resumo financeiro do período
**Como** gestor financeiro  
**Quero** ver um painel com os totais do mês  
**Para** entender rapidamente minha situação financeira  

**Critérios de aceite:**
- [ ] KPI: total de receitas do período
- [ ] KPI: total de despesas do período
- [ ] KPI: saldo (receitas − despesas)
- [ ] KPI: total a pagar (despesas pendentes)
- [ ] Navegação por mês com setas anterior/próximo
- [ ] Filtros por status: todos, pendentes, pagos, receitas, despesas

---

### HU-16 — Lançar despesas parceladas
**Como** gestor financeiro  
**Quero** registrar uma compra parcelada de uma só vez  
**Para** não precisar lançar cada parcela manualmente  

**Critérios de aceite:**
- [ ] Seleção de número de parcelas
- [ ] Sistema gera automaticamente todas as parcelas com vencimentos mensais
- [ ] Cada parcela numerada (ex: 1/12, 2/12...)
- [ ] Parcelas criadas como pendentes

---

### HU-17 — Exportar relatório financeiro
**Como** gestor financeiro  
**Quero** exportar meus lançamentos em Excel ou PDF  
**Para** compartilhar relatórios com terceiros ou arquivar  

**Critérios de aceite:**
- [ ] Exportação em Excel (.xlsx) com colunas formatadas
- [ ] Exportação em PDF com cabeçalho e tabela estilizada
- [ ] Arquivo baixado automaticamente
- [ ] Relatório contém apenas os dados do usuário autenticado

---

### HU-18 — Categorizar despesas
**Como** gestor financeiro  
**Quero** criar categorias para organizar meus lançamentos  
**Para** analisar onde estou gastando mais  

**Critérios de aceite:**
- [ ] Criação de categorias personalizadas
- [ ] Listagem das categorias do usuário
- [ ] Associação de categoria ao criar/editar um lançamento
- [ ] Exclusão de categoria (sem impactar lançamentos existentes)

---

### HU-19 — Controlar dívidas de terceiros
**Como** gestor financeiro  
**Quero** registrar valores que terceiros me devem  
**Para** não perder o controle de quem me deve e quando  

**Critérios de aceite:**
- [ ] Cadastro com: devedor, descrição, valor, vencimento e status
- [ ] Listagem de todas as dívidas do usuário
- [ ] Edição de qualquer campo da dívida
- [ ] Exclusão de dívida com confirmação

---

## Épico 5 — Controle de Combustível

### HU-20 — Registrar abastecimento
**Como** usuário corporativo  
**Quero** registrar cada abastecimento do meu veículo  
**Para** acompanhar meu consumo e gastos com combustível  

**Critérios de aceite:**
- [ ] Formulário com: data, tipo de combustível, KM atual, litros, valor unitário, valor total, forma de pagamento e flag tanque cheio
- [ ] Cálculo automático da distância percorrida (KM atual − KM do abastecimento anterior)
- [ ] Cálculo automático da média de consumo (km/l) quando tanque cheio
- [ ] Abastecimentos pagos à vista (pix, débito, dinheiro) lançados automaticamente no módulo financeiro como despesa paga

---

### HU-21 — Visualizar histórico e estatísticas de consumo
**Como** usuário corporativo  
**Quero** ver meu histórico de abastecimentos com estatísticas  
**Para** entender a performance do meu veículo e otimizar custos  

**Critérios de aceite:**
- [ ] Listagem de abastecimentos com filtro por mês/ano
- [ ] Exibição de mediana de consumo para gasolina e etanol separadamente
- [ ] Dados de km percorrida e média de cada abastecimento na listagem
- [ ] Exclusão de registro de abastecimento

---

## Backlog Priorizado

| Prioridade | HU | Módulo | Complexidade |
|-----------|-----|--------|-------------|
| 🔴 Alta | HU-01, HU-02 | Auth | Baixa |
| 🔴 Alta | HU-03, HU-04, HU-05 | Admin | Média |
| 🟡 Média | HU-10, HU-11, HU-12, HU-13 | Credenciais | Média |
| 🟡 Média | HU-14, HU-15, HU-16, HU-17 | Financeiro | Alta |
| 🟡 Média | HU-18, HU-19 | Financeiro | Baixa |
| 🟢 Baixa | HU-06, HU-07, HU-08, HU-09 | Email | Alta |
| 🟢 Baixa | HU-20, HU-21 | Combustível | Média |

---

**Total de histórias:** 21  
**Épicos:** 5  
**Status:** Todas implementadas ✅
