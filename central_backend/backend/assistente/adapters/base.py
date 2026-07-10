from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LlmResponse:
    content: str = ""
    tool_calls: list = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""
    error: Optional[str] = None


@dataclass
class ToolCall:
    name: str
    arguments: dict = field(default_factory=dict)


AGENDAMENTO_TOOLS_SCHEMA = [
    {
        "name": "buscar_horarios_disponiveis",
        "description": "Busca horários livres na agenda numa data específica. Use quando o usuário quiser marcar uma reunião, compromisso ou consulta.",
        "parameters": {
            "type": "object",
            "properties": {
                "data": {"type": "string", "description": "Data no formato YYYY-MM-DD"},
                "service_id": {"type": "integer", "description": "ID do tipo de compromisso desejado"},
            },
            "required": ["data", "service_id"],
        },
    },
    {
        "name": "pre_reservar_horario",
        "description": "Faz uma pré-reserva de 5 minutos para o horário escolhido pelo usuário, antes da confirmação final.",
        "parameters": {
            "type": "object",
            "properties": {
                "service_id": {"type": "integer", "description": "ID do tipo de compromisso"},
                "data_hora": {"type": "string", "description": "Data e hora no formato YYYY-MM-DD HH:MM"},
            },
            "required": ["service_id", "data_hora"],
        },
    },
    {
        "name": "confirmar_agendamento",
        "description": "Confirma um compromisso pré-reservado depois que o usuário disser que sim, pode marcar.",
        "parameters": {
            "type": "object",
            "properties": {
                "appointment_id": {"type": "integer", "description": "ID do compromisso pré-reservado"},
            },
            "required": ["appointment_id"],
        },
    },
    {
        "name": "cancelar_agendamento",
        "description": "Cancela o próximo compromisso ativo. Use quando o usuário quiser desmarcar.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "reagendar_agendamento",
        "description": "Muda o próximo compromisso ativo para uma nova data/hora.",
        "parameters": {
            "type": "object",
            "properties": {
                "nova_data_hora": {"type": "string", "description": "Nova data e hora no formato YYYY-MM-DD HH:MM"},
            },
            "required": ["nova_data_hora"],
        },
    },
    {
        "name": "consultar_agenda",
        "description": "Consulta os compromissos confirmados ou pré-reservados dos próximos dias. Use sempre que o usuário perguntar o que tem agendado, se tem algo marcado, ou pedir a agenda — nunca responda essa pergunta sem chamar essa função.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
]


FINANCEIRO_TOOLS_SCHEMA = [
    {
        "name": "registrar_gasto",
        "description": "Registra um gasto ou receita financeira relatada pelo usuário (ex: 'gastei 50 no mercado', 'recebi 500 de salário').",
        "parameters": {
            "type": "object",
            "properties": {
                "descricao": {"type": "string", "description": "O que foi o gasto/receita"},
                "valor": {"type": "number", "description": "Valor em reais"},
                "forma_pagamento": {"type": "string", "description": "debito|credito|pix|dinheiro|vale_alimentacao"},
                "natureza": {"type": "string", "description": "despesa ou receita"},
                "status": {"type": "string", "description": "paga ou pendente"},
                "vencimento": {"type": "string", "description": "Data de vencimento YYYY-MM-DD, se pendente"},
            },
            "required": ["descricao", "valor", "forma_pagamento"],
        },
    },
    {
        "name": "consultar_financas",
        "description": "Consulta o resumo financeiro do mês atual (receitas, despesas, saldo, contas pendentes). Use quando o usuário perguntar sobre gastos, saldo ou contas.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
]
