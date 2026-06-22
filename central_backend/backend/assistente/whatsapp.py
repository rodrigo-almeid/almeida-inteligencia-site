import httpx

API_BASE = "https://graph.facebook.com/v21.0"


async def enviar_mensagem(token: str, phone_id: str, to: str, text: str):
    url = f"{API_BASE}/{phone_id}/messages"
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": text},
            },
        )
        if not res.is_success:
            print(f"[whatsapp] erro ao enviar: {res.text}")


async def baixar_midia(token: str, media_id: str) -> bytes:
    async with httpx.AsyncClient(timeout=30) as client:
        meta_res = await client.get(
            f"{API_BASE}/{media_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        meta_res.raise_for_status()
        url = meta_res.json()["url"]

        media_res = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        media_res.raise_for_status()
        return media_res.content
