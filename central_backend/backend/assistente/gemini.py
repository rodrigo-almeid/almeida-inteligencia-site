import json
import base64
import httpx
from datetime import date

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

historico: dict[str, list] = {}


async def _gerar_groq(api_key: str, messages: list) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": GROQ_MODEL, "messages": messages},
        )
        res.raise_for_status()
        data = res.json()
        return data["choices"][0]["message"]["content"]


async def _gerar_gemini(api_key: str, contents: list) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(
            f"{GEMINI_URL}?key={api_key}",
            json={"contents": contents},
        )
        res.raise_for_status()
        data = res.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


def _get_keys(config):
    groq_key = config.groq_api_key if config and hasattr(config, 'groq_api_key') else None
    gemini_key = config.gemini_api_key if config else None
    return groq_key, gemini_key


async def _gerar(config, messages_groq: list, contents_gemini: list) -> str:
    groq_key, gemini_key = _get_keys(config)

    if groq_key:
        try:
            return await _gerar_groq(groq_key, messages_groq)
        except Exception:
            pass

    if gemini_key:
        return await _gerar_gemini(gemini_key, contents_gemini)

    raise Exception("Nenhuma API key configurada (Groq ou Gemini)")


def montar_system_prompt(config=None) -> str:
    nome = "Goku"
    tom = "casual"
    personalidade = ""
    instrucoes = ""

    if config:
        nome = config.nome_assistente or "Goku"
        tom = config.tom_voz or "casual"
        personalidade = config.personalidade or ""
        instrucoes = config.instrucoes_extras or ""

    tons = {
        "formal": "Responda de forma profissional, educada e formal.",
        "casual": "Responda de forma amigável, descontraída e direta.",
        "tecnico": "Responda de forma técnica e precisa, com termos específicos quando necessário.",
        "humoristico": "Responda com bom humor, use analogias divertidas, mas sem perder a utilidade.",
    }
    tom_texto = tons.get(tom, tons["casual"])

    prompt = (
        f"Você é {nome}, um assistente pessoal inteligente. "
        f"{tom_texto} "
        "Você ajuda com: conversas gerais, finanças pessoais e agenda. "
        "Está integrado ao sistema Almeida Inteligência. "
        "Responda sempre em português brasileiro."
    )

    if personalidade:
        prompt += f"\n\nSua personalidade: {personalidade}"
    if instrucoes:
        prompt += f"\n\nInstruções adicionais: {instrucoes}"

    return prompt


async def chat(api_key: str, user_id: str, mensagem: str, config=None) -> str:
    system = montar_system_prompt(config)
    nome = config.nome_assistente if config and config.nome_assistente else "Goku"

    if user_id not in historico:
        historico[user_id] = []
    hist = historico[user_id]

    messages_groq = [
        {"role": "system", "content": system},
        *[{"role": m["role"], "content": m["content"]} for m in hist[-10:]],
        {"role": "user", "content": mensagem},
    ]

    contents_gemini = [
        {"role": "user", "parts": [{"text": system}]},
        {"role": "model", "parts": [{"text": f"Entendido! Sou o {nome}. Como posso ajudar?"}]},
        *[{"role": m["role_gemini"], "parts": [{"text": m["content"]}]} for m in hist[-10:]],
        {"role": "user", "parts": [{"text": mensagem}]},
    ]

    resposta = await _gerar(config, messages_groq, contents_gemini)

    hist.append({"role": "user", "role_gemini": "user", "content": mensagem})
    hist.append({"role": "assistant", "role_gemini": "model", "content": resposta})
    if len(hist) > 20:
        del hist[:len(hist) - 20]

    return resposta


async def detectar_intencao(api_key: str, texto: str, config=None) -> str:
    intencoes = ["financeiro_consulta", "financeiro_registro", "agenda", "chat"]

    prompt = (
        f"Classifique a mensagem em UMA das intenções: {', '.join(intencoes)}.\n\n"
        "- financeiro_consulta: perguntas sobre gastos, quanto gastou, resumo financeiro\n"
        "- financeiro_registro: registrar gasto (ex: 'gastei 50 no mercado')\n"
        "- agenda: criar, listar ou editar eventos\n"
        "- chat: qualquer outra coisa\n\n"
        f'Mensagem: "{texto}"\n\n'
        "Responda APENAS com a intenção."
    )

    messages_groq = [{"role": "user", "content": prompt}]
    contents_gemini = [{"role": "user", "parts": [{"text": prompt}]}]

    resultado = (await _gerar(config, messages_groq, contents_gemini)).strip().lower()
    return resultado if resultado in intencoes else "chat"


async def extrair_dados_nota(api_key: str, image_bytes: bytes, mime_type: str = "image/jpeg", config=None) -> dict | None:
    prompt = (
        "Analise esta imagem de nota fiscal e extraia em JSON:\n"
        '{"estabelecimento":"nome","data":"YYYY-MM-DD","valor_total":0.00,'
        '"categoria":"alimentacao|transporte|saude|lazer|moradia|educacao|roupas|outros",'
        '"itens":[{"descricao":"nome","valor":0.00}]}\n'
        "Responda APENAS com o JSON."
    )

    # Visão só funciona com Gemini
    groq_key, gemini_key = _get_keys(config)
    if gemini_key:
        contents = [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode()}},
            ],
        }]
        texto = await _gerar_gemini(gemini_key, contents)
    else:
        return None

    texto = texto.strip().removeprefix("```json").removesuffix("```").strip()

    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return None


async def extrair_dados_gasto(api_key: str, texto: str, config=None) -> dict | None:
    hoje = date.today().isoformat()
    prompt = (
        "Extraia do texto abaixo as informações de gasto em JSON:\n"
        '{"descricao":"o que foi","valor":0.00,'
        '"categoria":"alimentacao|transporte|saude|lazer|moradia|educacao|roupas|outros",'
        f'"estabelecimento":"onde (ou null)","data":"YYYY-MM-DD (hoje: {hoje})"}}\n'
        f'Texto: "{texto}"\nResponda APENAS com o JSON.'
    )

    messages_groq = [{"role": "user", "content": prompt}]
    contents_gemini = [{"role": "user", "parts": [{"text": prompt}]}]

    resultado = await _gerar(config, messages_groq, contents_gemini)
    resultado = resultado.strip().removeprefix("```json").removesuffix("```").strip()

    try:
        return json.loads(resultado)
    except json.JSONDecodeError:
        return None
