import httpx
from backend.agendamento.crypto import decrypt_key


async def enviar_mensagem(token_cifrado: str, phone_id: str, to: str, text: str):
    token = decrypt_key(token_cifrado)
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            f"https://graph.facebook.com/v21.0/{phone_id}/messages",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": text},
            },
        )
