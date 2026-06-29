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


async def baixar_midia(media_url: str) -> bytes:
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(media_url)
        res.raise_for_status()
        return res.content
