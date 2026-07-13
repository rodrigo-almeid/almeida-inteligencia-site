import hmac
import hashlib
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class WebhookSignatureMiddleware(BaseHTTPMiddleware):
    """Valida a assinatura HMAC SHA-256 (X-Hub-Signature-256) que a Meta envia
    no POST do webhook do WhatsApp. Checa o path exato (não substring "webhook")
    pra não colidir com /agendamento/google/webhook (push notification do
    Google Calendar), que não manda essa assinatura."""

    async def dispatch(self, request: Request, call_next):
        if request.method == "POST" and request.url.path == "/assistente/webhook":
            app_secret = os.getenv("WHATSAPP_APP_SECRET", "")
            if app_secret:
                signature = request.headers.get("X-Hub-Signature-256", "")
                if not signature.startswith("sha256="):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Assinatura ausente ou inválida"},
                    )
                body = await request.body()
                expected = "sha256=" + hmac.new(
                    app_secret.encode(), body, hashlib.sha256,
                ).hexdigest()
                if not hmac.compare_digest(signature, expected):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Assinatura inválida"},
                    )
        return await call_next(request)
