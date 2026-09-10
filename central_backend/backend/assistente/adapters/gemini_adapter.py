import httpx
import json
from .base import LlmResponse, ToolCall


def _build_gemini_tools(tools_schema: list) -> list:
    return [{
        "function_declarations": [
            {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            }
            for t in tools_schema
        ]
    }]


def _build_contents(messages: list[dict]) -> list[dict]:
    contents = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    return contents


async def call(messages: list[dict], system_prompt: str, api_key: str, tools_schema: list = None, timeout: float = 8.0) -> LlmResponse:
    contents = _build_contents(messages)

    body = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024},
    }
    if tools_schema:
        body["tools"] = _build_gemini_tools(tools_schema)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}",
                json=body,
            )

        if res.status_code != 200:
            return LlmResponse(error=f"Gemini HTTP {res.status_code}: {res.text[:300]}")

        data = res.json()
        candidate = data.get("candidates", [{}])[0]
        parts = candidate.get("content", {}).get("parts", [])

        usage = data.get("usageMetadata", {})
        tokens_in = usage.get("promptTokenCount", 0)
        tokens_out = usage.get("candidatesTokenCount", 0)

        tool_calls = []
        text_parts = []

        for part in parts:
            if "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append(ToolCall(name=fc["name"], arguments=fc.get("args", {})))
            elif "text" in part:
                text_parts.append(part["text"])

        return LlmResponse(
            content="\n".join(text_parts),
            tool_calls=tool_calls,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model="gemini-2.5-flash",
        )

    except httpx.TimeoutException:
        return LlmResponse(error="Gemini timeout")
    except Exception as e:
        return LlmResponse(error=f"Gemini error: {str(e)}")
