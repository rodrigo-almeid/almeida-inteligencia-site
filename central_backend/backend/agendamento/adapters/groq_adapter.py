import httpx
import json
from .base import LlmResponse, ToolCall, TOOLS_SCHEMA


def _build_openai_tools():
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in TOOLS_SCHEMA
    ]


async def call(messages: list[dict], system_prompt: str, api_key: str, timeout: float = 8.0) -> LlmResponse:
    oai_messages = [{"role": "system", "content": system_prompt}]
    for m in messages:
        oai_messages.append({"role": m["role"], "content": m["content"]})

    body = {
        "model": "llama-3.1-8b-instant",
        "messages": oai_messages,
        "tools": _build_openai_tools(),
        "tool_choice": "auto",
        "max_tokens": 1024,
        "temperature": 0.3,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
            )

        if res.status_code != 200:
            return LlmResponse(error=f"Groq HTTP {res.status_code}: {res.text[:300]}")

        data = res.json()
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})

        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)

        tool_calls = []
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                args = fn.get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                tool_calls.append(ToolCall(name=fn.get("name", ""), arguments=args))

        return LlmResponse(
            content=msg.get("content", "") or "",
            tool_calls=tool_calls,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model="llama-3.1-8b-instant",
        )

    except httpx.TimeoutException:
        return LlmResponse(error="Groq timeout")
    except Exception as e:
        return LlmResponse(error=f"Groq error: {str(e)}")
