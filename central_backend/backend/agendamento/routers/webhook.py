import asyncio
from fastapi import APIRouter, Request, Response, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from backend.core import models
from backend.core.database import get_db, SessionLocal
from backend.agendamento.llm_gateway import processar_mensagem
from backend.agendamento.whatsapp import enviar_mensagem

router = APIRouter(prefix="/agendamento", tags=["Agendamento - Webhook"])


def _get_config_by_phone_id(phone_id: str, db: Session):
    return db.query(models.AgendamentoConfig).filter(
        models.AgendamentoConfig.whatsapp_phone_id == phone_id,
        models.AgendamentoConfig.ativo == True,
    ).first()


def _get_or_create_client(config_id: int, telefone: str, nome: str, db: Session) -> models.Client:
    client = db.query(models.Client).filter(
        models.Client.config_id == config_id,
        models.Client.telefone == telefone,
    ).first()
    if not client:
        client = models.Client(config_id=config_id, telefone=telefone, nome=nome)
        db.add(client)
        db.commit()
        db.refresh(client)
    return client


@router.get("/webhook")
def webhook_verify(request: Request, db: Session = Depends(get_db)):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode != "subscribe" or not token:
        raise HTTPException(status_code=403, detail="Verificação inválida")

    config = db.query(models.AgendamentoConfig).filter(
        models.AgendamentoConfig.whatsapp_verify_token == token,
        models.AgendamentoConfig.ativo == True,
    ).first()

    if not config:
        raise HTTPException(status_code=403, detail="Token de verificação inválido")

    return Response(content=challenge, media_type="text/plain")


@router.post("/webhook")
async def webhook_receive(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    body = await request.json()

    entry = (body.get("entry") or [{}])[0]
    changes = (entry.get("changes") or [{}])[0]
    value = changes.get("value", {})

    if "messages" not in value:
        return {"status": "no messages"}

    phone_id = value.get("metadata", {}).get("phone_number_id")
    config = _get_config_by_phone_id(phone_id, db)

    if not config:
        return {"status": "config not found"}

    for msg in value["messages"]:
        from_number = msg.get("from")
        contact_name = ""
        contacts = value.get("contacts", [])
        if contacts:
            contact_name = contacts[0].get("profile", {}).get("name", "")

        msg_type = msg.get("type")

        if msg_type != "text":
            resposta = config.mensagem_midia_bloqueada or "Desculpe, só consigo atender mensagens de texto."
            background_tasks.add_task(
                enviar_mensagem, config.whatsapp_token, config.whatsapp_phone_id, from_number, resposta,
            )
            continue

        texto = msg.get("text", {}).get("body", "")
        if not texto:
            continue

        background_tasks.add_task(
            _processar_em_background, config.id, from_number, contact_name, texto,
        )

    return {"status": "ok"}


async def _processar_em_background(config_id: int, telefone: str, nome: str, texto: str):
    db = SessionLocal()
    try:
        config = db.query(models.AgendamentoConfig).filter(
            models.AgendamentoConfig.id == config_id,
        ).first()
        if not config:
            return

        client = _get_or_create_client(config.id, telefone, nome, db)

        try:
            resposta = await processar_mensagem(texto, config, client, db)
        except Exception as e:
            print(f"[agendamento] Erro ao processar: {e}")
            import traceback
            traceback.print_exc()
            resposta = config.mensagem_contingencia or "Desculpe, tive um problema. Tente novamente."

        await enviar_mensagem(config.whatsapp_token, config.whatsapp_phone_id, telefone, resposta)
    finally:
        db.close()
