import httpx
from fastapi import APIRouter, Request, Response, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core import models
from backend.core.database import get_db
from backend.assistente.gemini import chat, detectar_intencao, extrair_dados_nota, extrair_dados_gasto
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


async def processar_mensagem(msg, config, user, db):
    tipo = msg.get("type")
    texto = msg.get("text", {}).get("body", "")

    if tipo == "image":
        media_id = msg.get("image", {}).get("id")
        mime = msg.get("image", {}).get("mime_type", "image/jpeg")
        buffer = await baixar_midia(config.whatsapp_token, media_id)
        dados = await extrair_dados_nota(config.gemini_api_key, buffer, mime)

        if not dados or not dados.get("valor_total"):
            return "Não consegui identificar uma nota fiscal nessa imagem. Tente uma foto mais nítida."

        salvar_compra_mercado(dados, user, db)
        return formatar_nota(dados)

    if not texto:
        return None

    intencao = await detectar_intencao(config.gemini_api_key, texto)

    if intencao == "financeiro_consulta":
        return consultar_financeiro(user, db)

    if intencao == "financeiro_registro":
        dados = await extrair_dados_gasto(config.gemini_api_key, texto)
        if not dados or not dados.get("valor") or dados["valor"] <= 0:
            return 'Não entendi o gasto. Tente: "gastei 50 reais no mercado"'
        salvar_conta(dados, user, db)
        return f"✅ Registrado!\n• {dados['descricao']}\n• R$ {dados['valor']:.2f}\n• Data: {dados.get('data', 'hoje')}"

    return await chat(config.gemini_api_key, msg.get("from"), texto, config)


def consultar_financeiro(user, db):
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

    if not do_mes:
        return f"Nenhuma conta registrada em {mes}/{ano}."

    total = sum(c.valor for c in do_mes)
    por_status = {}
    for c in do_mes:
        s = c.status or "sem status"
        por_status[s] = por_status.get(s, 0) + c.valor

    linhas = "\n".join(f"• {s}: R$ {v:.2f}" for s, v in sorted(por_status.items(), key=lambda x: -x[1]))
    return f"💰 *Resumo de {mes}/{ano}:*\n\n{linhas}\n\n*Total: R$ {total:.2f}*"


def salvar_conta(dados, user, db):
    from datetime import date
    hoje = date.today()
    venc_str = dados.get("data", hoje.isoformat())

    nova = models.Conta(
        descricao=dados["descricao"],
        vencimento=date.fromisoformat(venc_str),
        valor=dados["valor"],
        natureza="despesa",
        status="pago",
        tipo_recorrencia="unica",
        user_id=user.id,
    )
    db.add(nova)
    db.commit()


def salvar_compra_mercado(dados, user, db):
    from datetime import date
    compra = models.CompraSupermercado(
        data=dados.get("data", date.today().isoformat()),
        loja=dados.get("estabelecimento"),
        forma_pagamento="debito",
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


def formatar_nota(dados):
    itens = dados.get("itens", [])
    itens_txt = ""
    if itens:
        itens_txt = "\n\n*Itens:*\n" + "\n".join(
            f"• {i.get('descricao') or i.get('nome')}: R$ {i.get('valor', 0):.2f}" for i in itens
        )
    return (
        f"✅ *Nota registrada!*\n\n"
        f"🏪 {dados.get('estabelecimento', 'N/I')}\n"
        f"📅 {dados.get('data', 'N/I')}\n"
        f"💰 Total: R$ {dados['valor_total']:.2f}\n"
        f"🏷️ Categoria: {dados.get('categoria', 'outros')}"
        f"{itens_txt}"
    )
