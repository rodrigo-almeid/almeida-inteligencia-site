import httpx

GRAPH_API_VERSION = "v21.0"


async def enviar_mensagem(token: str, phone_id: str, to: str, text: str):
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_id}/messages"
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
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30) as client:
        meta_res = await client.get(
            f"https://graph.facebook.com/{GRAPH_API_VERSION}/{media_id}",
            headers=headers,
        )
        meta_res.raise_for_status()
        media_url = meta_res.json().get("url")
        if not media_url:
            raise ValueError("Meta não retornou a URL da mídia")

        file_res = await client.get(media_url, headers=headers)
        file_res.raise_for_status()
        return file_res.content
