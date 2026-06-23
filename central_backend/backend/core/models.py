from sqlalchemy import Column, Integer, String, Float, ForeignKey, Date, Boolean, UniqueConstraint, Table, Text, DateTime
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


# =====================================================================
# BLOCO 0: RBAC — PERFIS DE ACESSO
# =====================================================================

user_perfis = Table(
    "user_perfis",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("perfil_id", Integer, ForeignKey("perfis.id", ondelete="CASCADE"), primary_key=True),
)


class Perfil(Base):
    __tablename__ = "perfis"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, unique=True, nullable=False)  # dashboard | abastecimento | senhas | games

    users = relationship("User", secondary=user_perfis, back_populates="perfis")


# =====================================================================
# BLOCO 1: AUTENTICAÇÃO E GERENCIADOR DE SENHAS
# =====================================================================

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    # Relacionamentos
    perfis = relationship("Perfil", secondary=user_perfis, back_populates="users")
    pessoas = relationship("Pessoa", back_populates="user", cascade="all, delete-orphan")
    categorias = relationship("Categoria", back_populates="user", cascade="all, delete-orphan")
    contas = relationship("Conta", back_populates="user", cascade="all, delete-orphan")
    dividas = relationship("DividaTerceiro", back_populates="user", cascade="all, delete-orphan")
    agendamento_config = relationship("AgendamentoConfig", back_populates="user", uselist=False, cascade="all, delete-orphan")


class Pessoa(Base):
    __tablename__ = 'pessoas'

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    principal = Column(Boolean, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False)

    # Relacionamentos
    user = relationship("User", back_populates="pessoas")
    senhas = relationship("Senha", back_populates="pessoa", cascade="all, delete-orphan")
    dados_pessoais = relationship("DadoPessoal", back_populates="pessoa", cascade="all, delete-orphan")


class Senha(Base):
    __tablename__ = 'senhas'

    id = Column(Integer, primary_key=True, index=True)
    sistema = Column(String, nullable=False)
    usuario_sistema = Column(String, nullable=False)
    senha_criptografada = Column(String, nullable=False)
    pessoa_id = Column(Integer, ForeignKey('pessoas.id', ondelete="CASCADE"), nullable=False)

    # Relacionamentos
    pessoa = relationship("Pessoa", back_populates="senhas")


class DadoPessoal(Base):
    __tablename__ = 'dados_pessoais'

    id = Column(Integer, primary_key=True, index=True)
    chave = Column(String, nullable=False)
    valor = Column(String, nullable=False)
    pessoa_id = Column(Integer, ForeignKey('pessoas.id', ondelete="CASCADE"), nullable=False)

    # Relacionamentos
    pessoa = relationship("Pessoa", back_populates="dados_pessoais")


# =====================================================================
# BLOCO 2: ASSISTENTE DE CONTAS E FINANÇAS
# =====================================================================

class Categoria(Base):
    __tablename__ = 'categorias'
    __table_args__ = (UniqueConstraint('user_id', 'nome', name='uq_categorias_user_nome'),)

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=True)

    # Relacionamentos
    user = relationship("User", back_populates="categorias")
    contas = relationship("Conta", back_populates="categoria")


class Conta(Base):
    __tablename__ = 'contas'

    id = Column(Integer, primary_key=True, index=True)
    descricao = Column(String, nullable=False)
    vencimento = Column(Date, nullable=False)
    competencia = Column(String, nullable=True)  # formato "YYYY-MM", ex: "2025-07"
    valor = Column(Float, nullable=False)
    natureza = Column(String)  # Recebe os dados do ENUM tiponatureza
    status = Column(String)  # Recebe os dados do ENUM statusconta
    tipo_recorrencia = Column(String)  # Recebe os dados do ENUM tiporecorrencia
    parcela_atual = Column(Integer)
    total_parcelas = Column(Integer)
    mes_seguinte_processado = Column(Integer)

    # Chaves Estrangeiras
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=True)
    categoria_id = Column(Integer, ForeignKey('categorias.id', ondelete="SET NULL"), nullable=True)

    # Relacionamentos
    user = relationship("User", back_populates="contas")
    categoria = relationship("Categoria", back_populates="contas")


class DividaTerceiro(Base):
    __tablename__ = 'dividas_terceiros'

    id = Column(Integer, primary_key=True, index=True)
    devedor = Column(String, nullable=False)
    descricao = Column(String, nullable=False)
    vencimento = Column(Date, nullable=False)
    valor = Column(Float, nullable=False)
    status = Column(String)
    tipo_recorrencia = Column(String)
    parcela_atual = Column(Integer)
    total_parcelas = Column(Integer)
    mes_seguinte_processado = Column(Integer)

    # Chave Estrangeira
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=True)

    # Relacionamentos
    user = relationship("User", back_populates="dividas")

    # Adicione no final do seu models.py
class Abastecimento(Base):
    __tablename__ = "abastecimentos"

    id = Column(Integer, primary_key=True, index=True)
    data = Column(String, index=True)
    tipo_combustivel = Column(String)
    km_atual = Column(Float)
    litros = Column(Float)
    valor_unitario = Column(Float)
    valor_total = Column(Float)
    forma_pagamento = Column(String)
    tanque_cheio = Column(Boolean, default=True)

    km_anterior = Column(Float, nullable=True)
    distancia_percorrida = Column(Float, nullable=True)
    media_consumo = Column(Float, nullable=True)

    user_id = Column(Integer, ForeignKey("users.id"))


# =====================================================================
# BLOCO 4: MERCADO (COMPRAS DE SUPERMERCADO)
# =====================================================================

class CompraSupermercado(Base):
    __tablename__ = "compras_supermercado"

    id = Column(Integer, primary_key=True, index=True)
    data = Column(String, nullable=False, index=True)  # "YYYY-MM-DD"
    loja = Column(String, nullable=True)
    forma_pagamento = Column(String, nullable=False)  # debito | credito | vale_alimentacao
    bandeira_vale = Column(String, nullable=True)     # ticket | alelo | caju (se vale_alimentacao)
    valor_total = Column(Float, nullable=False, default=0.0)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    itens = relationship("ItemCompra", back_populates="compra", cascade="all, delete-orphan")


class ItemCompra(Base):
    __tablename__ = "itens_compra"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    valor = Column(Float, nullable=False)
    categoria = Column(String, nullable=True)

    compra_id = Column(Integer, ForeignKey("compras_supermercado.id", ondelete="CASCADE"), nullable=False)
    compra = relationship("CompraSupermercado", back_populates="itens")


# =====================================================================
# BLOCO 5: ASSISTENTE VIRTUAL (GOKU)
# =====================================================================

class AssistenteConfig(Base):
    __tablename__ = "assistente_config"

    id = Column(Integer, primary_key=True, index=True)
    whatsapp_token = Column(String, nullable=True)
    whatsapp_phone_id = Column(String, nullable=True)
    whatsapp_verify_token = Column(String, nullable=True)
    gemini_api_key = Column(String, nullable=True)
    groq_api_key = Column(String, nullable=True)
    numero_autorizado = Column(String, nullable=True)
    ativo = Column(Boolean, default=False)

    nome_assistente = Column(String, nullable=True, default="Goku")
    personalidade = Column(String, nullable=True)
    tom_voz = Column(String, nullable=True, default="casual")
    instrucoes_extras = Column(String, nullable=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)


# =====================================================================
# BLOCO 6: AGENDAMENTO INTELIGENTE + GESTÃO DE LLMs
# =====================================================================

class AgendamentoConfig(Base):
    __tablename__ = "agendamento_config"

    id = Column(Integer, primary_key=True, index=True)
    whatsapp_token = Column(String, nullable=True)
    whatsapp_phone_id = Column(String, nullable=True)
    whatsapp_verify_token = Column(String, nullable=True)
    gemini_api_key = Column(String, nullable=True)
    groq_api_key = Column(String, nullable=True)
    ollama_url = Column(String, nullable=True)
    ollama_model = Column(String, nullable=True)
    prioridade_llms = Column(String, nullable=True, default='["gemini","groq","ollama"]')
    gemini_ativo = Column(Boolean, default=False)
    groq_ativo = Column(Boolean, default=False)
    ollama_ativo = Column(Boolean, default=False)
    catalogo_prompt = Column(Text, nullable=True)
    mensagem_midia_bloqueada = Column(String, nullable=True, default="Desculpe, no momento só consigo atender mensagens de texto.")
    mensagem_contingencia = Column(String, nullable=True, default="Olá! No momento estamos com instabilidade no atendimento automático. Tente novamente em alguns minutos.")
    ativo = Column(Boolean, default=False)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    user = relationship("User", back_populates="agendamento_config")
    horarios = relationship("HorarioFuncionamento", back_populates="config", cascade="all, delete-orphan")
    servicos = relationship("Service", back_populates="config", cascade="all, delete-orphan")
    clients = relationship("Client", back_populates="config", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="config", cascade="all, delete-orphan")
    messages = relationship("ConversationMessage", back_populates="config", cascade="all, delete-orphan")
    llm_logs = relationship("LlmLog", back_populates="config", cascade="all, delete-orphan")


class HorarioFuncionamento(Base):
    __tablename__ = "horarios_funcionamento"

    id = Column(Integer, primary_key=True, index=True)
    dia_semana = Column(Integer, nullable=False)
    hora_inicio = Column(String, nullable=False)
    hora_fim = Column(String, nullable=False)
    ativo = Column(Boolean, default=True)

    config_id = Column(Integer, ForeignKey("agendamento_config.id", ondelete="CASCADE"), nullable=False)
    config = relationship("AgendamentoConfig", back_populates="horarios")


class Service(Base):
    __tablename__ = "agendamento_servicos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    descricao = Column(String, nullable=True)
    duracao_minutos = Column(Integer, nullable=False)
    preco = Column(Float, nullable=True)
    ativo = Column(Boolean, default=True)

    config_id = Column(Integer, ForeignKey("agendamento_config.id", ondelete="CASCADE"), nullable=False)
    config = relationship("AgendamentoConfig", back_populates="servicos")
    appointments = relationship("Appointment", back_populates="service")


class Client(Base):
    __tablename__ = "agendamento_clients"
    __table_args__ = (UniqueConstraint("config_id", "telefone", name="uq_client_config_telefone"),)

    id = Column(Integer, primary_key=True, index=True)
    telefone = Column(String, nullable=False, index=True)
    nome = Column(String, nullable=True)
    criado_em = Column(DateTime, server_default="now()")

    config_id = Column(Integer, ForeignKey("agendamento_config.id", ondelete="CASCADE"), nullable=False)
    config = relationship("AgendamentoConfig", back_populates="clients")
    appointments = relationship("Appointment", back_populates="client")
    messages = relationship("ConversationMessage", back_populates="client")


class Appointment(Base):
    __tablename__ = "agendamento_appointments"

    id = Column(Integer, primary_key=True, index=True)
    data_hora = Column(DateTime, nullable=False, index=True)
    status = Column(String, nullable=False, default="pre_reservado")
    expires_at = Column(DateTime, nullable=True)
    lembrete_enviado = Column(Boolean, default=False)
    criado_em = Column(DateTime, server_default="now()")

    config_id = Column(Integer, ForeignKey("agendamento_config.id", ondelete="CASCADE"), nullable=False)
    client_id = Column(Integer, ForeignKey("agendamento_clients.id", ondelete="CASCADE"), nullable=False)
    service_id = Column(Integer, ForeignKey("agendamento_servicos.id", ondelete="SET NULL"), nullable=True)

    config = relationship("AgendamentoConfig", back_populates="appointments")
    client = relationship("Client", back_populates="appointments")
    service = relationship("Service", back_populates="appointments")


class ConversationMessage(Base):
    __tablename__ = "agendamento_messages"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    llm_provider = Column(String, nullable=True)
    criado_em = Column(DateTime, server_default="now()")

    config_id = Column(Integer, ForeignKey("agendamento_config.id", ondelete="CASCADE"), nullable=False)
    client_id = Column(Integer, ForeignKey("agendamento_clients.id", ondelete="CASCADE"), nullable=False)

    config = relationship("AgendamentoConfig", back_populates="messages")
    client = relationship("Client", back_populates="messages")


class LlmLog(Base):
    __tablename__ = "agendamento_llm_logs"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=True)
    status_code = Column(Integer, nullable=True)
    tokens_in = Column(Integer, nullable=True)
    tokens_out = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    erro = Column(Text, nullable=True)
    criado_em = Column(DateTime, server_default="now()")

    config_id = Column(Integer, ForeignKey("agendamento_config.id", ondelete="CASCADE"), nullable=False)
    config = relationship("AgendamentoConfig", back_populates="llm_logs")