"""Execução das tools financeiras chamadas pelo llm_gateway — wrappers finos
sobre backend.assistente.finance_actions (lógica determinística já testada,
não delegada ao LLM: só o "o que fazer" é decidido pelo modelo)."""
from backend.assistente.adapters.base import ToolCall
from backend.assistente import finance_actions

NOMES_TOOLS = {"registrar_gasto", "consultar_financas"}


async def executar(tool_call: ToolCall, user, db) -> str:
    if tool_call.name == "registrar_gasto":
        return _registrar_gasto(tool_call.arguments, user, db)
    if tool_call.name == "consultar_financas":
        return finance_actions.montar_resumo_financeiro(user, db)
    return f"Função '{tool_call.name}' não reconhecida."


def _registrar_gasto(args: dict, user, db) -> str:
    dados = {
        "descricao": args.get("descricao"),
        "valor": args.get("valor"),
        "forma_pagamento": args.get("forma_pagamento"),
        "natureza": args.get("natureza") or "despesa",
        "status": args.get("status") or "paga",
        "vencimento": args.get("vencimento"),
    }
    faltantes = finance_actions.validar_registro(dados)
    if faltantes:
        return f"Faltam os campos: {', '.join(faltantes)}. Peça esses dados ao cliente antes de tentar de novo."

    finance_actions.salvar_registro_financeiro(dados, user, db)
    return f"Registrado: {dados['descricao']} — R$ {float(dados['valor']):.2f} ({dados['forma_pagamento']})."
