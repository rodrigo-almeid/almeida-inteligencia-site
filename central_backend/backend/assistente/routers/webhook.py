import json
import httpx
from fastapi import APIRouter, Request, Response, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core import models
from backend.core.database import get_db
from backend.assistente.gemini import (
    chat, detectar_intencao, extrair_dados_nota, extrair_dados_gasto,
    humanizar_confirmacao, perguntar_campos_faltantes, complementar_dados,
    _gerar,
)
from backend.assistente.whatsapp import enviar_mensagem, baixar_midia

router = APIRouter(prefix="/assistente", tags=["Assistente Virtual"])


def get_config_by_phone_id(phone_id: str, db: Session):
    return db.query(models.AssistenteConfig).filter(
        models.AssistenteConfig.whatsapp_phone_id == phone_id,
        models.AssistenteConfig.ativo == True
    ).first()


@router.get("/webhook")
def webhook_verify(request: Request, db: Session = Depends(get_db)):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode != "subscribe" or not token:
        raise HTTPException(status_code=403, detail="Verificação inválida")

    config = db.query(models.AssistenteConfig).filter(
        models.AssistenteConfig.whatsapp_verify_token == token,
        models.AssistenteConfig.ativo == True
    ).first()

    if not config:
        raise HTTPException(status_code=403, detail="Token de verificação inválido")

    return Response(content=challenge, media_type="text/plain")


@router.post("/webhook")
async def webhook_receive(request: Request, db: Session = Depends(get_db)):
    body = await request.json()

    entry = (body.get("entry") or [{}])[0]
    changes = (entry.get("changes") or [{}])[0]
    value = changes.get("value", {})

    if "messages" not in value:
        return {"status": "no messages"}

    phone_id = value.get("metadata", {}).get("phone_number_id")
    print(f"[goku] webhook recebido. phone_id={phone_id}")

    config = get_config_by_phone_id(phone_id, db)

    if not config:
        print(f"[goku] config NAO encontrada para phone_id={phone_id}")
        return {"status": "config not found"}

    print(f"[goku] config encontrada. user_id={config.user_id}, ativo={config.ativo}")
    user = db.query(models.User).filter(models.User.id == config.user_id).first()

    for msg in value["messages"]:
        from_number = msg.get("from")
        print(f"[goku] mensagem de {from_number}, autorizado={config.numero_autorizado}")

        if from_number != config.numero_autorizado:
            print(f"[goku] BLOQUEADO - numero nao autorizado")
            continue

        try:
            print(f"[goku] processando mensagem: {msg.get('text', {}).get('body', '')}")
            reply = await processar_mensagem(msg, config, user, db)
            print(f"[goku] resposta gerada: {reply[:100] if reply else 'None'}")
            if reply:
                await enviar_mensagem(config.whatsapp_token, config.whatsapp_phone_id, from_number, reply)
                print(f"[goku] mensagem enviada para {from_number}")
        except Exception as e:
            print(f"[goku] ERRO: {e}")
            import traceback
            traceback.print_exc()
            await enviar_mensagem(config.whatsapp_token, config.whatsapp_phone_id, from_number,
                                  "Desculpe, tive um problema. Tente novamente.")

    return {"status": "ok"}


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


async def processar_mensagem(msg, config, user, db):
    tipo = msg.get("type")
    texto = msg.get("text", {}).get("body", "")

    if tipo == "image":
        media_id = msg.get("image", {}).get("id")
        mime = msg.get("image", {}).get("mime_type", "image/jpeg")
        buffer = await baixar_midia(config.whatsapp_token, media_id)
        dados = await extrair_dados_nota(config.gemini_api_key, buffer, mime, config)

        if not dados or not dados.get("valor_total"):
            return "Não consegui identificar uma nota fiscal nessa imagem. Tente uma foto mais nítida."

        _limpar_pendente(user.id, db)
        return processar_nota_fiscal(dados, user, db)

    if not texto:
        return None

    pendente = _get_pendente(user.id, db)
    if pendente:
        return await _processar_com_pendente(pendente, texto, config, user, db)

    intencao = await detectar_intencao(config.gemini_api_key, texto, config)

    if intencao == "financeiro_consulta":
        return await consultar_financeiro(texto, user, db, config)

    if intencao == "financeiro_registro":
        dados = await extrair_dados_gasto(config.gemini_api_key, texto, config)
        if not dados:
            return await chat(config.gemini_api_key, msg.get("from"), texto, config)

        faltantes = validar_registro(dados)
        if not faltantes:
            salvar_conta(dados, user, db)
            return await humanizar_confirmacao(dados, dados.get("forma_pagamento"), config)

        _salvar_pendente(user.id, dados, faltantes, db)
        return await perguntar_campos_faltantes(dados, faltantes, config)

    return await chat(config.gemini_api_key, msg.get("from"), texto, config)


async def _processar_com_pendente(pendente, texto, config, user, db):
    dados_atuais = json.loads(pendente.dados_json)
    campos_faltantes = json.loads(pendente.campos_faltantes)

    texto_lower = texto.strip().lower()
    if texto_lower in ("cancelar", "cancela", "deixa", "esquece", "para"):
        desc = dados_atuais.get("descricao", "registro")
        _limpar_pendente(user.id, db)
        return f"Beleza, cancelei o registro de *{desc}*! 👍"

    novos = await complementar_dados(dados_atuais, campos_faltantes, texto, config)

    if not novos:
        intencao = await detectar_intencao(config.gemini_api_key, texto, config)
        if intencao in ("financeiro_consulta", "financeiro_registro", "agenda"):
            desc = dados_atuais.get("descricao", "registro")
            nome = config.nome_assistente if config and config.nome_assistente else "Goku"
            return (
                f"Ei, você ainda tem o registro de *{desc}* pendente. "
                "Quer cancelar e seguir com outra coisa? (responde 'cancelar' ou me manda o que falta)"
            )
        return await perguntar_campos_faltantes(dados_atuais, campos_faltantes, config)

    for k, v in novos.items():
        if v and v != "null":
            dados_atuais[k] = v

    faltantes = validar_registro(dados_atuais)
    if not faltantes:
        _limpar_pendente(user.id, db)
        salvar_conta(dados_atuais, user, db)
        return await humanizar_confirmacao(dados_atuais, dados_atuais.get("forma_pagamento"), config)

    _salvar_pendente(user.id, dados_atuais, faltantes, db)
    return await perguntar_campos_faltantes(dados_atuais, faltantes, config)


async def consultar_financeiro(texto, user, db, config=None):
    from datetime import date
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

    dados_financeiros = (
        f"Mês: {mes}/{ano}\n"
        f"Total de receitas: R$ {total_receitas:.2f}\n"
        f"Total de despesas: R$ {total_despesas:.2f}\n"
        f"Saldo (receitas - despesas): R$ {saldo:.2f}\n"
        f"Total já pago: R$ {total_pago:.2f}\n"
        f"Total pendente: R$ {total_pendente:.2f}\n"
        f"Contas vencendo hoje ({hoje.strftime('%d/%m')}): {len(vencendo_hoje)}\n"
    )

    if vencendo_hoje:
        dados_financeiros += "\nDetalhes das contas de hoje:\n"
        for c in vencendo_hoje:
            dados_financeiros += f"  - {c.descricao}: R$ {c.valor:.2f}\n"

    if pendentes:
        dados_financeiros += f"\nPróximas contas pendentes ({len(pendentes)}):\n"
        pendentes_ord = sorted(pendentes, key=lambda c: c.vencimento or hoje)
        for c in pendentes_ord[:10]:
            venc = c.vencimento.strftime("%d/%m") if c.vencimento else "sem data"
            dados_financeiros += f"  - {c.descricao}: R$ {c.valor:.2f} (vence {venc})\n"

    nome = config.nome_assistente if config and config.nome_assistente else "Goku"
    prompt = (
        f"Você é o {nome}, assistente financeiro no WhatsApp. "
        f"O usuário perguntou: \"{texto}\"\n\n"
        f"Dados financeiros do mês atual:\n{dados_financeiros}\n"
        "Responda a pergunta do usuário de forma direta e natural, como um amigo. "
        "Use os dados acima para dar uma resposta precisa. "
        "Formate valores como R$ X.XX. Use emoji com moderação (1-2). "
        "Se o usuário perguntou sobre vencimentos de hoje e não tem nenhum, diga que está tranquilo. "
        "Seja breve — máximo 4-5 linhas."
    )

    messages = [{"role": "user", "content": prompt}]
    contents = [{"role": "user", "parts": [{"text": prompt}]}]

    try:
        return await _gerar(config, messages, contents)
    except Exception:
        linhas = []
        if vencendo_hoje:
            linhas.append(f"📅 *Vencendo hoje ({hoje.strftime('%d/%m')}):*")
            for c in vencendo_hoje:
                linhas.append(f"  • {c.descricao}: R$ {c.valor:.2f}")
        else:
            linhas.append(f"✅ Nenhuma conta vencendo hoje!")
        linhas.append(f"\n💰 *Resumo {mes}/{ano}:*")
        linhas.append(f"  • Receitas: R$ {total_receitas:.2f}")
        linhas.append(f"  • Despesas: R$ {total_despesas:.2f}")
        linhas.append(f"  • Saldo: R$ {saldo:.2f}")
        if total_pendente > 0:
            linhas.append(f"  • Pendente: R$ {total_pendente:.2f}")
        return "\n".join(linhas)


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


def salvar_conta(dados, user, db):
    from datetime import date
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
    from datetime import date
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
    from datetime import date
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
