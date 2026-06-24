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


async def _gerar_ollama(url: str, model: str, messages: list) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            f"{url.rstrip('/')}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
        )
        res.raise_for_status()
        return res.json()["message"]["content"]


def _get_provedores(config) -> list[dict]:
    if config and hasattr(config, 'provedores_llm') and config.provedores_llm:
        raw = config.provedores_llm
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                raw = []
        if isinstance(raw, list):
            return [p for p in raw if (p.get("ativo", True) if isinstance(p, dict) else getattr(p, "ativo", True))]
    return _provedores_legado(config)


def _provedores_legado(config) -> list[dict]:
    result = []
    if config:
        if getattr(config, 'gemini_api_key', None):
            result.append({"tipo": "gemini", "api_key": config.gemini_api_key})
        if getattr(config, 'groq_api_key', None):
            result.append({"tipo": "groq", "api_key": config.groq_api_key})
        if getattr(config, 'ollama_url', None) and getattr(config, 'ollama_model', None):
            result.append({"tipo": "ollama", "url": config.ollama_url, "modelo": config.ollama_model})
    return result


def _get(p, key):
    return p.get(key) if isinstance(p, dict) else getattr(p, key, None)


async def _gerar(config, messages_groq: list, contents_gemini: list) -> str:
    provedores = _get_provedores(config)
    last_error = None

    for p in provedores:
        tipo = _get(p, "tipo")
        try:
            if tipo == "gemini" and _get(p, "api_key"):
                return await _gerar_gemini(_get(p, "api_key"), contents_gemini)
            elif tipo == "groq" and _get(p, "api_key"):
                return await _gerar_groq(_get(p, "api_key"), messages_groq)
            elif tipo == "ollama" and _get(p, "url"):
                modelo = _get(p, "modelo") or "llama3"
                return await _gerar_ollama(_get(p, "url"), modelo, messages_groq)
        except Exception as e:
            last_error = e
            continue

    raise Exception(f"Nenhum provedor de IA disponível. Último erro: {last_error}")


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


async def humanizar_confirmacao(dados: dict, forma: str = None, config=None) -> str:
    pgto_map = {"debito": "débito", "credito": "crédito", "pix": "Pix", "dinheiro": "dinheiro", "vale_alimentacao": "vale alimentação"}
    pgto = pgto_map.get(forma or dados.get("forma_pagamento", ""), "")
    natureza = dados.get("natureza", "despesa")
    status = dados.get("status", "paga")
    nome = config.nome_assistente if config and config.nome_assistente else "Goku"

    prompt = (
        f"Você é o {nome}, assistente pessoal no WhatsApp. "
        "O usuário acabou de registrar um lançamento financeiro e você precisa confirmar de forma breve, "
        "natural e amigável (1-2 frases curtas, como uma conversa de WhatsApp). "
        "Use emoji com moderação (1-2 no máximo). Não repita todos os campos, só o essencial.\n\n"
        f"Dados do registro:\n"
        f"- Descrição: {dados.get('descricao')}\n"
        f"- Valor: R$ {dados.get('valor', 0):.2f}\n"
        f"- Natureza: {natureza}\n"
        f"- Status: {status}\n"
        f"- Data: {dados.get('data', dados.get('vencimento', 'hoje'))}\n"
    )
    if pgto:
        prompt += f"- Pagamento: {pgto}\n"

    messages_groq = [{"role": "user", "content": prompt}]
    contents_gemini = [{"role": "user", "parts": [{"text": prompt}]}]

    try:
        return await _gerar(config, messages_groq, contents_gemini)
    except Exception:
        return f"✅ *{dados.get('descricao')}* registrada — R$ {dados.get('valor', 0):.2f}"


async def humanizar_confirmacao_sem_pgto(dados: dict, config=None) -> str:
    nome = config.nome_assistente if config and config.nome_assistente else "Goku"
    natureza = dados.get("natureza", "despesa")

    prompt = (
        f"Você é o {nome}, assistente pessoal no WhatsApp. "
        "O usuário registrou um lançamento financeiro mas NÃO disse a forma de pagamento. "
        "Confirme o registro de forma breve e natural (1-2 frases), e pergunte a forma de pagamento "
        "de forma casual, como um amigo perguntaria (ex: 'foi no pix, cartão ou dinheiro?'). "
        "Use emoji com moderação. Não liste opções numeradas.\n\n"
        f"Dados do registro:\n"
        f"- Descrição: {dados.get('descricao')}\n"
        f"- Valor: R$ {dados.get('valor', 0):.2f}\n"
        f"- Natureza: {natureza}\n"
    )

    messages_groq = [{"role": "user", "content": prompt}]
    contents_gemini = [{"role": "user", "parts": [{"text": prompt}]}]

    try:
        return await _gerar(config, messages_groq, contents_gemini)
    except Exception:
        return f"✅ Registrei *{dados.get('descricao')}* — R$ {dados.get('valor', 0):.2f}\nFoi no pix, cartão ou dinheiro?"


NOMES_CAMPOS = {
    "descricao": "o que foi (descrição)",
    "valor": "o valor em reais",
    "forma_pagamento": "a forma de pagamento (pix, cartão, débito, dinheiro, vale)",
}


async def perguntar_campos_faltantes(dados_parciais: dict, campos_faltantes: list[str], config=None) -> str:
    nome = config.nome_assistente if config and config.nome_assistente else "Goku"

    preenchidos = []
    for k, v in dados_parciais.items():
        if v and v != "null":
            preenchidos.append(f"{k}: {v}")

    faltam_desc = [NOMES_CAMPOS.get(c, c) for c in campos_faltantes]

    prompt = (
        f"Você é o {nome}, assistente financeiro no WhatsApp. "
        "O usuário está registrando um lançamento financeiro mas faltam algumas informações.\n\n"
        f"Dados já informados: {', '.join(preenchidos) if preenchidos else 'nenhum ainda'}\n"
        f"Campos faltantes: {', '.join(faltam_desc)}\n\n"
        "Pergunte ao usuário APENAS o que falta, de forma natural e breve (1-2 frases). "
        "Seja como um amigo perguntando no WhatsApp. Use 1 emoji no máximo. "
        "Se já tem a descrição, mencione ela na pergunta para contextualizar. "
        "NÃO liste opções numeradas. Seja conversacional."
    )

    messages = [{"role": "user", "content": prompt}]
    contents = [{"role": "user", "parts": [{"text": prompt}]}]

    try:
        return await _gerar(config, messages, contents)
    except Exception:
        return f"Preciso de mais info: {', '.join(faltam_desc)}. Me conta?"


async def complementar_dados(dados_atuais: dict, campos_faltantes: list[str], mensagem: str, config=None) -> dict:
    campos_desc = {c: NOMES_CAMPOS.get(c, c) for c in campos_faltantes}

    prompt = (
        "O usuário está completando um registro financeiro. "
        f"Dados já preenchidos: {json.dumps(dados_atuais, ensure_ascii=False)}\n"
        f"Campos que FALTAM preencher: {json.dumps(campos_desc, ensure_ascii=False)}\n"
        f"Nova mensagem do usuário: \"{mensagem}\"\n\n"
        "Extraia da mensagem APENAS os campos faltantes e retorne em JSON. "
        "Regras:\n"
        "- valor: número com 2 casas decimais\n"
        "- forma_pagamento: debito|credito|pix|dinheiro|vale_alimentacao\n"
        "- descricao: texto curto descrevendo o gasto/receita\n"
        "- 'cartão' sem especificar = 'credito'\n"
        "- '1'='debito', '2'='credito', '3'='pix', '4'='dinheiro', '5'='vale_alimentacao'\n"
        "Responda APENAS com o JSON dos campos extraídos. Se não conseguiu extrair nada, retorne {}"
    )

    messages = [{"role": "user", "content": prompt}]
    contents = [{"role": "user", "parts": [{"text": prompt}]}]

    try:
        resultado = await _gerar(config, messages, contents)
        resultado = resultado.strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(resultado)
    except Exception:
        return {}


async def detectar_intencao(api_key: str, texto: str, config=None) -> str:
    intencoes = ["financeiro_consulta", "financeiro_registro", "agenda", "chat"]

    prompt = (
        f"Classifique a mensagem em UMA das intenções: {', '.join(intencoes)}.\n\n"
        "- financeiro_registro: o usuário RELATA um gasto, compra, conta, boleto OU uma receita/entrada que aconteceu ou vai acontecer. "
        "Palavras-chave: gastei, paguei, comprei, almocei, conta de, boleto, parcela, vence, fatura, pila, conto, mango, real, reais, "
        "recebi, ganhei, me pagaram, entrou, salário, freelance, vendi, reembolso, apostei, perdi, bet, assinei, emprestei, rendeu, resgatei.\n"
        "  Exemplos: 'gastei 50 no mercado', 'paguei 30 de uber', 'conta de luz 180', 'eita gastei uns 30 pila', "
        "'comprei um tênis por 250', 'almocei por 28 reais', 'recebi 5000 de salário', 'me pagaram 500 do freelance', "
        "'apostei 40 e perdi', 'perdi 50 na bet', 'ganhei 200 na aposta', 'assinei netflix 55', 'rendeu 150 do investimento'\n\n"
        "- financeiro_consulta: o usuário PERGUNTA sobre seus gastos ou quer um resumo. "
        "Palavras-chave: quanto, total, resumo, extrato, saldo, como estão, minhas contas.\n"
        "  Exemplos: 'quanto gastei esse mês?', 'como estão minhas contas?', 'qual meu saldo?'\n\n"
        "- agenda: criar, listar ou editar eventos, reuniões, compromissos\n"
        "- chat: qualquer outra coisa (saudações, perguntas gerais, conversa)\n\n"
        "IMPORTANTE: se a mensagem contém um VALOR em dinheiro e um VERBO financeiro "
        "(gastei, paguei, comprei, recebi, ganhei, perdi, apostei, assinei, emprestei, rendeu), "
        "é SEMPRE financeiro_registro, mesmo que tenha gírias ou tom informal.\n\n"
        f'Mensagem: "{texto}"\n\n'
        "Responda APENAS com a intenção, uma única palavra."
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
        '"tipo_estabelecimento":"mercado|restaurante|farmacia|posto|loja|outro",'
        '"forma_pagamento":"debito|credito|vale_alimentacao|pix|dinheiro|outro",'
        '"bandeira_vale":"ticket|alelo|caju|sodexo|null",'
        '"itens":[{"descricao":"nome","valor":0.00}]}\n'
        "Regras para tipo_estabelecimento: se for supermercado, hipermercado, atacadão, mercearia = 'mercado'.\n"
        "Regras para forma_pagamento: identifique pela nota se possível. Se não conseguir, use 'debito'.\n"
        "Responda APENAS com o JSON."
    )

    gemini_key = _get_gemini_key(config)
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


def _get_gemini_key(config) -> str | None:
    provedores = _get_provedores(config)
    for p in provedores:
        if _get(p, "tipo") == "gemini" and _get(p, "api_key"):
            return _get(p, "api_key")
    if config and getattr(config, 'gemini_api_key', None):
        return config.gemini_api_key
    return None


async def extrair_dados_gasto(api_key: str, texto: str, config=None) -> dict | None:
    hoje = date.today().isoformat()
    prompt = (
        "Extraia do texto abaixo as informações financeiras em JSON:\n"
        '{"descricao":"o que foi","valor":0.00,'
        '"natureza":"despesa|receita",'
        '"categoria":"alimentacao|transporte|saude|lazer|moradia|educacao|roupas|assinatura|aposta|salario|freelance|investimento|venda|reembolso|outros",'
        f'"estabelecimento":"onde (ou null)","data":"YYYY-MM-DD (hoje: {hoje})",'
        '"status":"paga|pendente",'
        '"vencimento":"YYYY-MM-DD ou null se já pago",'
        '"forma_pagamento":"debito|credito|pix|dinheiro|vale_alimentacao|null"}\n'
        "Regras de natureza:\n"
        "- despesa: gastei, paguei, comprei, conta de, boleto, parcela, fatura, apostei e perdi, perdi na bet, assinei, emprestei\n"
        "- receita: recebi, ganhei, me pagaram, entrou, salário, freelance, vendi, reembolso, ganhei na aposta/bet, rendeu, resgatei\n"
        "Regras de status: se o usuário diz 'gastei', 'paguei', 'comprei', 'recebi' = status 'paga'. "
        "Se diz 'conta de', 'vence', 'parcela', 'boleto', 'vou receber' = status 'pendente' e preencha vencimento.\n"
        "Regras forma_pagamento: se o usuário mencionar explicitamente (pix, cartão, débito, crédito, dinheiro, vale), preencha. "
        "Se não mencionar, use null.\n"
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
