from pydantic import BaseModel, EmailStr, ConfigDict
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import date

# =====================================================================
# CONFIGURAÇÃO BASE (Permite que o Pydantic leia modelos do SQLAlchemy)
# =====================================================================
class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

# =====================================================================
# BLOCO 1: AUTENTICAÇÃO E USUÁRIOS
# =====================================================================
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserResponse(ORMBase):
    id: int
    email: EmailStr

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class PerfilResponse(ORMBase):
    id: int
    nome: str

# =====================================================================
# BLOCO 2: PESSOAS E SENHAS
# =====================================================================
class PessoaCreate(BaseModel):
    nome: str
    principal: bool = False

class PessoaResponse(ORMBase):
    id: int
    nome: str
    principal: bool
    user_id: int

class SenhaCreate(BaseModel):
    sistema: str
    usuario_sistema: str
    senha: str  # Recebe a senha em texto plano do Front-end para o Back-end criptografar
    pessoa_id: int

class SenhaResponse(ORMBase):
    id: int
    sistema: str
    usuario_sistema: str
    pessoa_id: int
    senha_criptografada: str

class DadoDinamicoCreate(BaseModel):
    chave: str
    valor: str
    pessoa_id: int

class DadoDinamicoResponse(ORMBase):
    id: int
    chave: str
    valor: str
    pessoa_id: int


# =====================================================================
# BLOCO 3: ASSISTENTE DE CONTAS E FINANÇAS
# =====================================================================
class CategoriaCreate(BaseModel):
    nome: str

class CategoriaResponse(ORMBase):
    id: int
    nome: str
    user_id: int

class ContaCreate(BaseModel):
    descricao: str
    vencimento: date
    competencia: Optional[str] = None
    valor: float
    natureza: Optional[str] = None
    status: Optional[str] = None
    tipo_recorrencia: Optional[str] = None
    parcela_atual: Optional[int] = None
    total_parcelas: Optional[int] = None
    mes_seguinte_processado: Optional[int] = None
    categoria_id: Optional[int] = None

class ContaResponse(ORMBase):
    id: int
    descricao: str
    vencimento: date
    competencia: Optional[str]
    valor: float
    natureza: Optional[str]
    status: Optional[str]
    tipo_recorrencia: Optional[str]
    parcela_atual: Optional[int]
    total_parcelas: Optional[int]
    mes_seguinte_processado: Optional[int]
    categoria_id: Optional[int]
    user_id: int

class MigrarContasRequest(BaseModel):
    conta_ids: List[int]

class MigrarContasResponse(BaseModel):
    migradas: int
    novas_contas: List[ContaResponse]

class DividaCreate(BaseModel):
    devedor: str
    descricao: str
    vencimento: date
    valor: float
    status: Optional[str] = None
    tipo_recorrencia: Optional[str] = None
    parcela_atual: Optional[int] = None
    total_parcelas: Optional[int] = None
    mes_seguinte_processado: Optional[int] = None

class DividaResponse(ORMBase):
    id: int
    devedor: str
    descricao: str
    vencimento: date
    valor: float
    status: Optional[str]
    tipo_recorrencia: Optional[str]
    parcela_atual: Optional[int]
    total_parcelas: Optional[int]
    mes_seguinte_processado: Optional[int]
    user_id: int

# Adicione no seu schemas.py
from typing import Optional

class AbastecimentoCreate(BaseModel):
    data: str
    tipo_combustivel: str
    km_atual: float
    litros: float
    valor_unitario: float
    valor_total: float
    forma_pagamento: str
    tanque_cheio: bool

class AbastecimentoResponse(AbastecimentoCreate):
    id: int
    km_anterior: Optional[float] = None
    distancia_percorrida: Optional[float] = None
    media_consumo: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


# =====================================================================
# BLOCO 4: MERCADO
# =====================================================================

class ItemCompraCreate(BaseModel):
    nome: str
    valor: float
    categoria: Optional[str] = None

class ItemCompraResponse(ORMBase):
    id: int
    nome: str
    valor: float
    categoria: Optional[str]

class CompraCreate(BaseModel):
    data: str
    loja: Optional[str] = None
    forma_pagamento: str
    bandeira_vale: Optional[str] = None
    itens: List[ItemCompraCreate]

class CompraResponse(ORMBase):
    id: int
    data: str
    loja: Optional[str]
    forma_pagamento: str
    bandeira_vale: Optional[str]
    valor_total: float
    itens: List[ItemCompraResponse]


# =====================================================================
# BLOCO 5: ASSISTENTE VIRTUAL (GOKU)
# =====================================================================

class AssistenteProvedorLLM(BaseModel):
    tipo: str  # "gemini", "groq", "ollama"
    api_key: Optional[str] = None
    url: Optional[str] = None
    modelo: Optional[str] = None
    ativo: bool = True

class AssistenteConfigCreate(BaseModel):
    whatsapp_token: Optional[str] = None
    whatsapp_phone_id: Optional[str] = None
    whatsapp_verify_token: Optional[str] = None
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None
    provedores_llm: Optional[List[AssistenteProvedorLLM]] = None
    numero_autorizado: Optional[str] = None
    ativo: bool = False
    usar_tool_calling: bool = False
    nome_assistente: Optional[str] = "Goku"
    personalidade: Optional[str] = None
    tom_voz: Optional[str] = "casual"
    instrucoes_extras: Optional[str] = None
    bulma_ativo: bool = False
    bulma_nome_assistente: Optional[str] = "Bulma"
    bulma_personalidade: Optional[str] = None
    bulma_tom_voz: Optional[str] = "casual"
    bulma_instrucoes_extras: Optional[str] = None
    bulma_ollama_url: Optional[str] = None
    bulma_ollama_model: Optional[str] = None

class AssistenteConfigResponse(ORMBase):
    id: int
    whatsapp_token: Optional[str] = None
    whatsapp_phone_id: Optional[str] = None
    whatsapp_verify_token: Optional[str] = None
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None
    provedores_llm: Optional[List[AssistenteProvedorLLM]] = None
    numero_autorizado: Optional[str]
    ativo: bool
    usar_tool_calling: bool = False
    nome_assistente: Optional[str]
    personalidade: Optional[str]
    tom_voz: Optional[str]
    instrucoes_extras: Optional[str]
    bulma_ativo: bool = False
    bulma_nome_assistente: Optional[str] = None
    bulma_personalidade: Optional[str] = None
    bulma_tom_voz: Optional[str] = None
    bulma_instrucoes_extras: Optional[str] = None
    bulma_ollama_url: Optional[str] = None
    bulma_ollama_model: Optional[str] = None
    user_id: int


# =====================================================================
# BLOCO 6: AGENDAMENTO INTELIGENTE + GESTÃO DE LLMs
# =====================================================================

from datetime import datetime

class AgendamentoConfigCreate(BaseModel):
    catalogo_prompt: Optional[str] = None
    mensagem_midia_bloqueada: Optional[str] = None
    mensagem_contingencia: Optional[str] = None
    ativo: bool = False
    google_calendar_ativo: Optional[bool] = None

class AgendamentoConfigResponse(ORMBase):
    id: int
    catalogo_prompt: Optional[str]
    mensagem_midia_bloqueada: Optional[str]
    mensagem_contingencia: Optional[str]
    ativo: bool
    google_calendar_ativo: bool = False
    google_calendar_id: Optional[str] = None
    google_calendar_conectado: bool = False
    user_id: int

class HorarioFuncionamentoCreate(BaseModel):
    dia_semana: int
    hora_inicio: str
    hora_fim: str
    ativo: bool = True

class HorarioFuncionamentoResponse(ORMBase):
    id: int
    dia_semana: int
    hora_inicio: str
    hora_fim: str
    ativo: bool
    config_id: int

class ServiceCreate(BaseModel):
    nome: str
    descricao: Optional[str] = None
    duracao_minutos: int
    preco: Optional[float] = None
    ativo: bool = True

class ServiceResponse(ORMBase):
    id: int
    nome: str
    descricao: Optional[str]
    duracao_minutos: int
    preco: Optional[float]
    ativo: bool
    config_id: int

class ClientResponse(ORMBase):
    id: int
    telefone: str
    nome: Optional[str]
    criado_em: Optional[datetime]
    config_id: int

class AppointmentResponse(ORMBase):
    id: int
    data_hora: datetime
    status: str
    expires_at: Optional[datetime]
    lembrete_enviado: bool
    google_event_id: Optional[str] = None
    descricao: Optional[str] = None
    duracao_minutos: Optional[int] = None
    criado_em: Optional[datetime]
    config_id: int
    client_id: int
    service_id: Optional[int]
    cliente_nome: Optional[str] = None
    servico_nome: Optional[str] = None
    servico_duracao_minutos: Optional[int] = None

class AppointmentCreate(BaseModel):
    data_hora: datetime
    service_id: Optional[int] = None
    descricao: Optional[str] = None
    duracao_minutos: Optional[int] = None
    status: str = "confirmado"

class AppointmentUpdate(BaseModel):
    data_hora: Optional[datetime] = None
    service_id: Optional[int] = None
    descricao: Optional[str] = None
    duracao_minutos: Optional[int] = None
    status: Optional[str] = None

class ConversationMessageResponse(ORMBase):
    id: int
    role: str
    content: str
    llm_provider: Optional[str]
    criado_em: Optional[datetime]
    config_id: int
    client_id: int

class LlmLogResponse(ORMBase):
    id: int
    provider: str
    model: Optional[str]
    status_code: Optional[int]
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    latency_ms: Optional[int]
    erro: Optional[str]
    criado_em: Optional[datetime]
    config_id: int


# =====================================================================
# BLOCO 7: CARTÃO DE CRÉDITO
# =====================================================================

class CartaoCreate(BaseModel):
    nome: str
    ultimos_digitos: Optional[str] = None
    limite: Optional[float] = None
    dia_fechamento: int
    dia_vencimento: int

class CartaoResponse(ORMBase):
    id: int
    nome: str
    ultimos_digitos: Optional[str]
    limite: Optional[float]
    dia_fechamento: int
    dia_vencimento: int
    ativo: bool
    user_id: int

class FaturaCartaoResponse(ORMBase):
    id: int
    cartao_id: int
    mes_referencia: str
    valor_total: float
    conta_id: Optional[int]
    status: str
    user_id: int

class ItemFaturaCreate(BaseModel):
    fatura_id: int
    descricao: str
    valor: float
    data_compra: date
    categoria_id: Optional[int] = None

class ItemFaturaUpdate(BaseModel):
    descricao: str
    valor: float
    data_compra: date
    categoria_id: Optional[int] = None

class ItemFaturaResponse(ORMBase):
    id: int
    fatura_id: int
    descricao: str
    valor: float
    data_compra: date
    categoria_id: Optional[int]
    categoria: Optional[CategoriaResponse] = None
    user_id: int

class PagamentoFaturaCreate(BaseModel):
    fatura_id: int
    valor: float
    data_pagamento: date

class PagamentoFaturaResponse(ORMBase):
    id: int
    fatura_id: int
    valor: float
    data_pagamento: date
    user_id: int