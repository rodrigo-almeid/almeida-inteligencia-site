import json
import re
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


# Alguns modelos Llama (via Groq/Ollama) às vezes "escrevem" a chamada de
# função como texto em vez de usar o campo estruturado tool_calls da API —
# visto em produção com llama-3.1-8b-instant (Groq), em formatos variados e
# nem sempre bem-formados: `<function=nome>{...}</function>` (completo),
# `nome>{...}` (sem as tags) e até só `nome` sozinho (sem chaves nenhuma).
# Sem tratar isso, o texto cru (com uma "resposta" inventada pelo modelo,
# sem a função ter sido executada de verdade) ia direto pro usuário como se
# fosse a resposta real.
_FUNCTION_CALL_PATTERN = re.compile(r"(?:<function=)?([a-zA-Z_][\w-]*)>\s*(\{.*?\})\s*(?:</function>)?", re.DOTALL)


def extrair_tool_calls_de_texto(content: str, tools_schema: list = None) -> tuple:
    """Retorna (texto_sem_a_chamada, [ToolCall, ...]) — lista vazia se o
    conteúdo não tiver nenhuma chamada de função em formato de texto.

    Exige `tools_schema` (a lista de tools oferecidas nessa chamada) — sem
    tools oferecidas, não há chamada legítima possível, então não tenta
    detectar nada (evita falso-positivo na 2ª chamada de humanização, que é
    feita de propósito sem tools_schema).

    Quando encontra uma chamada, descarta TODO o texto ao redor (não só a
    tag) — esse texto foi escrito pelo modelo antes de saber o resultado
    real da função, então qualquer alegação nele (ex: "você já tem
    compromisso nesse horário") é invenção, não fato."""
    if not content or not tools_schema:
        return content, []

    nomes_validos = {t["name"] for t in tools_schema}

    matches = _FUNCTION_CALL_PATTERN.findall(content)
    tool_calls = []
    for nome, args_json in matches:
        if nome not in nomes_validos:
            continue
        try:
            args = json.loads(args_json)
        except json.JSONDecodeError:
            args = {}
        tool_calls.append(ToolCall(name=nome, arguments=args))

    if tool_calls:
        return "", tool_calls

    # Caso degenerado: o conteúdo inteiro é só o nome de uma função conhecida,
    # sem chaves nem argumento nenhum (ex: só "cancelar_agendamento").
    nome_bare = content.strip()
    if nome_bare in nomes_validos:
        return "", [ToolCall(name=nome_bare, arguments={})]

    return content, []


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
        "name": "marcar_compromisso",
        "description": "Marca um compromisso JÁ CONFIRMADO na hora, sem precisar de um segundo passo de confirmação do usuário. Use essa função sempre que o pedido de agendamento já for direto e claro (ex: 'marca uma reunião às 14', 'marca dentista amanhã de manhã'). Se já existir algo marcado nesse exato horário, a função retorna o conflito em vez de marcar — nesse caso, avise o usuário do conflito e sugira outro horário, não tente marcar de novo sem perguntar.",
        "parameters": {
            "type": "object",
            "properties": {
                "service_id": {"type": "integer", "description": "ID do tipo de compromisso"},
                "data_hora": {"type": "string", "description": "Data e hora no formato YYYY-MM-DD HH:MM"},
                "descricao": {"type": "string", "description": "Assunto/observação do compromisso, se o usuário mencionou (opcional)"},
            },
            "required": ["service_id", "data_hora"],
        },
    },
    {
        "name": "atualizar_compromisso",
        "description": "Atualiza o assunto/descrição de um compromisso já marcado (ex: 'coloca o assunto X na reunião das 14'). Localiza o compromisso pela data/hora informada, ou pelo próximo compromisso ativo se a hora não for clara.",
        "parameters": {
            "type": "object",
            "properties": {
                "descricao": {"type": "string", "description": "Novo assunto/descrição do compromisso"},
                "data_hora": {"type": "string", "description": "Data e hora do compromisso a atualizar, formato YYYY-MM-DD HH:MM (opcional — se não informado, usa o próximo compromisso ativo)"},
            },
            "required": ["descricao"],
        },
    },
    {
        "name": "pre_reservar_horario",
        "description": "Segura um horário por 5 minutos SEM confirmar ainda. Só use se o usuário pedir explicitamente pra 'segurar'/'ver antes de confirmar' um horário — pedidos diretos de marcar devem usar marcar_compromisso, não essa função.",
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
        "description": "Confirma um compromisso pré-reservado por pre_reservar_horario, depois que o usuário disser que sim, pode marcar.",
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
        "description": "Muda o próximo compromisso ativo para uma nova data/hora, mantendo o mesmo assunto e status (se já estava confirmado, o novo horário também já fica confirmado — sem pedir confirmação de novo).",
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
