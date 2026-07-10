import httpx
import json
from .base import LlmResponse, ToolCall


def _build_ollama_tools(tools_schema: list) -> list:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in tools_schema
    ]


async def call(messages: list[dict], system_prompt: str, url: str, model: str, tools_schema: list = None, timeout: float = 15.0) -> LlmResponse:
    ollama_messages = [{"role": "system", "content": system_prompt}]
    for m in messages:
        ollama_messages.append({"role": m["role"], "content": m["content"]})

    body = {
        "model": model,
        "messages": ollama_messages,
        "stream": False,
        "options": {"temperature": 0.3},
    }
    if tools_schema:
        body["tools"] = _build_ollama_tools(tools_schema)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.post(f"{url.rstrip('/')}/api/chat", json=body)

        if res.status_code != 200:
            return LlmResponse(error=f"Ollama HTTP {res.status_code}: {res.text[:300]}")

        data = res.json()
        msg = data.get("message", {})

        tool_calls = []
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                tool_calls.append(ToolCall(name=fn.get("name", ""), arguments=args))

        tokens_in = data.get("prompt_eval_count", 0)
        tokens_out = data.get("eval_count", 0)

        return LlmResponse(
            content=msg.get("content", "") or "",
            tool_calls=tool_calls,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=model,
        )

    except httpx.TimeoutException:
        return LlmResponse(error="Ollama timeout")
    except Exception as e:
        return LlmResponse(error=f"Ollama error: {str(e)}")
