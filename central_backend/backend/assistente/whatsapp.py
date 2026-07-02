import base64
import httpx


async def enviar_mensagem(evolution_url: str, api_key: str, instance: str, to: str, text: str):
    url = f"{evolution_url.rstrip('/')}/message/sendText/{instance}"
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.post(
            url,
            headers={"apikey": api_key, "Content-Type": "application/json"},
            json={
                "number": to,
                "text": text,
            },
        )
        if not res.is_success:
            print(f"[whatsapp] erro ao enviar: {res.text}")


async def baixar_midia(evolution_url: str, api_key: str, instance: str, message_data: dict) -> bytes:
    # No Baileys a mídia vem criptografada (imageMessage.url é um .enc no CDN do WhatsApp).
    # A própria mensagem do webhook já traz mediaKey/fileEncSha256 necessários para decriptar,
    # então repassamos key+message originais em vez de depender do store da Evolution API.
    url = f"{evolution_url.rstrip('/')}/chat/getBase64FromMediaMessage/{instance}"
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(
            url,
            headers={"apikey": api_key, "Content-Type": "application/json"},
            json={
                "message": {
                    "key": message_data.get("key", {}),
                    "message": message_data.get("message", {}),
                },
                "convertToMp4": False,
            },
        )
        res.raise_for_status()
        b64 = res.json().get("base64")
        if not b64:
            raise ValueError("Evolution API não retornou base64 da mídia")
        return base64.b64decode(b64)
