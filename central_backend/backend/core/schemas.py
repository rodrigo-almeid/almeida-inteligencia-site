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
    valor: float
    tipo_despesa: Optional[str] = None
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
    valor: float
    tipo_despesa: Optional[str]
    natureza: Optional[str]
    status: Optional[str]
    tipo_recorrencia: Optional[str]
    parcela_atual: Optional[int]
    total_parcelas: Optional[int]
    mes_seguinte_processado: Optional[int]
    categoria_id: Optional[int]
    user_id: int

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

    class Config:
        from_attributes = True # Se usar Pydantic v2 (se for v1, use orm_mode = True)