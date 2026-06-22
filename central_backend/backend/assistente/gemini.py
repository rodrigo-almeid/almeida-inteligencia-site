import json
import base64
import httpx
from datetime import date

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

historico: dict[str, list] = {}


async def _gerar(api_key: str, contents: list):
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(
            f"{GEMINI_URL}?key={api_key}",
            json={"contents": contents},
        )
        res.raise_for_status()
        data = res.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


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

    contents = [
        {"role": "user", "parts": [{"text": system}]},
        {"role": "model", "parts": [{"text": f"Entendido! Sou o {nome}. Como posso ajudar?"}]},
        *hist[-10:],
        {"role": "user", "parts": [{"text": mensagem}]},
    ]

    resposta = await _gerar(api_key, contents)

    hist.append({"role": "user", "parts": [{"text": mensagem}]})
    hist.append({"role": "model", "parts": [{"text": resposta}]})
    if len(hist) > 20:
        del hist[:len(hist) - 20]

    return resposta


async def detectar_intencao(api_key: str, mensagem: str) -> str:
    intencoes = ["financeiro_consulta", "financeiro_registro", "agenda", "chat"]

    prompt = (
        f"Classifique a mensagem em UMA das intenções: {', '.join(intencoes)}.\n\n"
        "- financeiro_consulta: perguntas sobre gastos, quanto gastou, resumo financeiro\n"
        "- financeiro_registro: registrar gasto (ex: 'gastei 50 no mercado')\n"
        "- agenda: criar, listar ou editar eventos\n"
        "- chat: qualquer outra coisa\n\n"
        f'Mensagem: "{mensagem}"\n\n'
        "Responda APENAS com a intenção."
    )

    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    resultado = (await _gerar(api_key, contents)).strip().lower()
    return resultado if resultado in intencoes else "chat"


async def extrair_dados_nota(api_key: str, image_bytes: bytes, mime_type: str = "image/jpeg") -> dict | None:
    prompt = (
        "Analise esta imagem de nota fiscal e extraia em JSON:\n"
        '{"estabelecimento":"nome","data":"YYYY-MM-DD","valor_total":0.00,'
        '"categoria":"alimentacao|transporte|saude|lazer|moradia|educacao|roupas|outros",'
        '"itens":[{"descricao":"nome","valor":0.00}]}\n'
        "Responda APENAS com o JSON."
    )

    contents = [{
        "role": "user",
        "parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode()}},
        ],
    }]

    texto = await _gerar(api_key, contents)
    texto = texto.strip().removeprefix("```json").removesuffix("```").strip()

    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return None


async def extrair_dados_gasto(api_key: str, texto: str) -> dict | None:
    hoje = date.today().isoformat()
    prompt = (
        "Extraia do texto abaixo as informações de gasto em JSON:\n"
        '{"descricao":"o que foi","valor":0.00,'
        '"categoria":"alimentacao|transporte|saude|lazer|moradia|educacao|roupas|outros",'
        f'"estabelecimento":"onde (ou null)","data":"YYYY-MM-DD (hoje: {hoje})"}}\n'
        f'Texto: "{texto}"\nResponda APENAS com o JSON.'
    )

    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    resultado = await _gerar(api_key, contents)
    resultado = resultado.strip().removeprefix("```json").removesuffix("```").strip()

    try:
        return json.loads(resultado)
    except json.JSONDecodeError:
        return None
