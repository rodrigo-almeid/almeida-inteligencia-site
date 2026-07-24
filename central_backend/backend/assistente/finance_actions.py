"""Lógica financeira pura do assistente — extraída de routers/webhook.py pra
poder ser reusada tanto pelo fluxo legado (detectar_intencao) quanto pela tool
registrar_gasto/consultar_financas do llm_gateway novo, sem duplicar código."""
import json
from datetime import date

from backend.core import models


CAMPOS_OBRIGATORIOS = ["descricao", "valor", "forma_pagamento"]


def validar_registro(dados: dict) -> list[str]:
    faltantes = []
    for campo in CAMPOS_OBRIGATORIOS:
        val = dados.get(campo)
        if val is None or val == "null" or val == "":
            faltantes.append(campo)
    valor = dados.get("valor")
    if valor is not None and valor != "null" and valor != "" and float(valor) <= 0:
        if "valor" not in faltantes:
            faltantes.append("valor")
    return faltantes


def _get_pendente(user_id, db):
    return db.query(models.RegistroPendente).filter(
        models.RegistroPendente.user_id == user_id
    ).first()


def _salvar_pendente(user_id, dados, campos_faltantes, db):
    pendente = _get_pendente(user_id, db)
    if pendente:
        pendente.dados_json = json.dumps(dados, ensure_ascii=False)
        pendente.campos_faltantes = json.dumps(campos_faltantes)
    else:
        pendente = models.RegistroPendente(
            user_id=user_id,
            dados_json=json.dumps(dados, ensure_ascii=False),
            campos_faltantes=json.dumps(campos_faltantes),
        )
        db.add(pendente)
    db.commit()


def _limpar_pendente(user_id, db):
    db.query(models.RegistroPendente).filter(
        models.RegistroPendente.user_id == user_id
    ).delete()
    db.commit()


def montar_resumo_financeiro(user, db) -> str:
    """Parte pura (sem chamada de LLM) do que era consultar_financeiro() em
    routers/webhook.py — coleta e calcula os dados financeiros do mês atual."""
    hoje = date.today()
    mes, ano = hoje.month, hoje.year

    contas = db.query(models.Conta).filter(
        models.Conta.user_id == user.id
    ).all()

    do_mes = [c for c in contas if (
        (c.competencia and c.competencia == f"{ano}-{mes:02d}")
        or (not c.competencia and c.vencimento and c.vencimento.month == mes and c.vencimento.year == ano)
    )]

    vencendo_hoje = [c for c in do_mes if c.vencimento == hoje and c.status != "paga"]
    pendentes = [c for c in do_mes if c.status == "pendente"]
    pagas = [c for c in do_mes if c.status == "paga"]

    total_despesas = sum(c.valor for c in do_mes if c.natureza == "despesa")
    total_receitas = sum(c.valor for c in do_mes if c.natureza == "receita")
    total_pendente = sum(c.valor for c in pendentes)
    total_pago = sum(c.valor for c in pagas)
    saldo = total_receitas - total_despesas

    resumo = (
        f"Mês: {mes}/{ano}\n"
        f"Total de receitas: R$ {total_receitas:.2f}\n"
        f"Total de despesas: R$ {total_despesas:.2f}\n"
        f"Saldo (receitas - despesas): R$ {saldo:.2f}\n"
        f"Total já pago: R$ {total_pago:.2f}\n"
        f"Total pendente: R$ {total_pendente:.2f}\n"
    )

    if vencendo_hoje:
        resumo += f"\nContas vencendo HOJE ({hoje.strftime('%d/%m')}):\n"
        for c in vencendo_hoje:
            resumo += f"  - {c.descricao}: R$ {c.valor:.2f}\n"
    else:
        resumo += f"Contas vencendo hoje ({hoje.strftime('%d/%m')}): nenhuma\n"

    if pendentes:
        pendentes_ord = sorted(pendentes, key=lambda c: c.vencimento or hoje)
        from itertools import groupby
        resumo += f"\nContas pendentes por data de vencimento ({len(pendentes)} total):\n"
        for venc_date, group in groupby(pendentes_ord[:20], key=lambda c: c.vencimento):
            data_str = venc_date.strftime("%d/%m") if venc_date else "sem data"
            itens = ", ".join(f"{c.descricao} R${c.valor:.2f}" for c in group)
            resumo += f"  {data_str}: {itens}\n"

    return resumo


def processar_nota_fiscal(dados, user, db):
    tipo_estab = dados.get("tipo_estabelecimento", "outro")
    forma_pgto = dados.get("forma_pagamento", "debito")
    eh_mercado = tipo_estab == "mercado"

    destinos = []

    if eh_mercado:
        salvar_compra_mercado(dados, user, db)
        destinos.append("Mercado")

        if forma_pgto == "debito":
            salvar_conta_from_nota(dados, user, db)
            destinos.append("Contas")
    else:
        salvar_conta_from_nota(dados, user, db)
        destinos.append("Contas")

    return formatar_nota(dados, destinos, forma_pgto)


def _eh_compra_de_mercado(dados) -> bool:
    return (
        dados.get("tipo_estabelecimento") == "mercado"
        and dados.get("natureza", "despesa") == "despesa"
    )


def salvar_registro_financeiro(dados, user, db):
    """Roteia o registro de texto pro módulo certo: compra de mercado (com
    espelho em Contas quando pago no débito, igual ao fluxo de nota fiscal
    em processar_nota_fiscal) ou conta normal."""
    if _eh_compra_de_mercado(dados):
        salvar_compra_mercado_de_texto(dados, user, db)
        if (dados.get("forma_pagamento") or "") == "debito":
            salvar_conta(dados, user, db)
        return

    salvar_conta(dados, user, db)


def salvar_compra_mercado_de_texto(dados, user, db):
    forma_pgto = dados.get("forma_pagamento") or "debito"
    if forma_pgto == "null":
        forma_pgto = "debito"
    bandeira = dados.get("bandeira_vale") if forma_pgto == "vale_alimentacao" else None

    compra = models.CompraSupermercado(
        data=dados.get("data") or date.today().isoformat(),
        loja=dados.get("estabelecimento"),
        forma_pagamento=forma_pgto,
        bandeira_vale=bandeira,
        valor_total=dados["valor"],
        user_id=user.id,
    )
    db.add(compra)
    db.commit()
    db.refresh(compra)
    return compra


def salvar_conta(dados, user, db):
    hoje = date.today()
    status = dados.get("status", "paga")
    venc_str = dados.get("vencimento") or dados.get("data") or hoje.isoformat()

    forma = dados.get("forma_pagamento")
    if forma == "null":
        forma = None

    nova = models.Conta(
        descricao=dados["descricao"],
        vencimento=date.fromisoformat(venc_str),
        valor=dados["valor"],
        natureza=dados.get("natureza", "despesa"),
        status=status,
        tipo_recorrencia="unica",
        origem="goku",
        forma_pagamento=forma,
        user_id=user.id,
    )
    db.add(nova)
    db.commit()
    db.refresh(nova)
    return nova


def salvar_conta_from_nota(dados, user, db):
    hoje = date.today()
    venc_str = dados.get("data") or hoje.isoformat()

    nova = models.Conta(
        descricao=f"{dados.get('estabelecimento', 'Compra')}",
        vencimento=date.fromisoformat(venc_str),
        valor=dados["valor_total"],
        natureza="despesa",
        status="paga",
        tipo_recorrencia="unica",
        origem="goku",
        user_id=user.id,
    )
    db.add(nova)
    db.commit()


def salvar_compra_mercado(dados, user, db):
    forma_pgto = dados.get("forma_pagamento", "debito")
    bandeira = dados.get("bandeira_vale") if forma_pgto == "vale_alimentacao" else None

    compra = models.CompraSupermercado(
        data=dados.get("data", date.today().isoformat()),
        loja=dados.get("estabelecimento"),
        forma_pagamento=forma_pgto,
        bandeira_vale=bandeira,
        valor_total=dados["valor_total"],
        user_id=user.id,
    )
    db.add(compra)
    db.flush()

    for item in dados.get("itens", []):
        db.add(models.ItemCompra(
            nome=item.get("descricao") or item.get("nome", "Item"),
            valor=item.get("valor", 0),
            categoria=dados.get("categoria"),
            compra_id=compra.id,
        ))

    db.commit()


def formatar_nota(dados, destinos, forma_pgto):
    itens = dados.get("itens", [])
    itens_txt = ""
    if itens:
        itens_txt = "\n\n*Itens:*\n" + "\n".join(
            f"• {i.get('descricao') or i.get('nome')}: R$ {i.get('valor', 0):.2f}" for i in itens
        )

    destinos_txt = " + ".join(destinos)
    pgto_map = {"debito": "Débito", "credito": "Crédito", "vale_alimentacao": "Vale Alimentação", "pix": "Pix", "dinheiro": "Dinheiro"}
    pgto_txt = pgto_map.get(forma_pgto, forma_pgto)

    return (
        f"✅ *Nota registrada!*\n\n"
        f"🏪 {dados.get('estabelecimento', 'N/I')}\n"
        f"📅 {dados.get('data', 'N/I')}\n"
        f"💰 Total: R$ {dados['valor_total']:.2f}\n"
        f"💳 Pagamento: {pgto_txt}\n"
        f"🏷️ Categoria: {dados.get('categoria', 'outros')}\n"
        f"📂 Salvo em: {destinos_txt}"
        f"{itens_txt}"
    )
