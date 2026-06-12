"""
Extrator IMAP universal — Gmail e Outlook/Exchange.
Busca e-mails que NÃO estejam na pasta 'Processado'.
Após salvar, move cópia para 'Processado' como flag de controle.
"""
import imaplib
import email
import email.header
import email.utils
import re

PASTA_PROCESSADO = "Processado"


def _decodificar_header(raw: str) -> str:
    partes = email.header.decode_header(raw or "")
    resultado = []
    for parte, charset in partes:
        if isinstance(parte, bytes):
            resultado.append(parte.decode(charset or "utf-8", errors="replace"))
        else:
            resultado.append(parte)
    return "".join(resultado).strip()


def _extrair_texto(msg: email.message.Message) -> str:
    corpo = []
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in disp:
                charset = part.get_content_charset() or "utf-8"
                corpo.append(part.get_payload(decode=True).decode(charset, errors="replace"))
    else:
        charset = msg.get_content_charset() or "utf-8"
        corpo.append(msg.get_payload(decode=True).decode(charset, errors="replace"))
    texto = "\n".join(corpo)
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"\s{3,}", "\n", texto)
    return texto.strip()


def _garantir_pasta(conn: imaplib.IMAP4_SSL, pasta: str):
    try:
        conn.create(pasta)
    except Exception:
        pass  # já existe


def _ids_ja_processados(conn: imaplib.IMAP4_SSL, pasta: str) -> set[str]:
    """Retorna o conjunto de Message-IDs que estão na pasta Processado."""
    ids = set()
    try:
        status, _ = conn.select(f'"{pasta}"', readonly=True)
        if status != "OK":
            return ids
        _, data = conn.uid("SEARCH", None, "ALL")
        uids = data[0].split() if data[0] else []
        for uid in uids:
            _, raw = conn.uid("FETCH", uid, "(BODY[HEADER.FIELDS (MESSAGE-ID)])")
            if raw and raw[0]:
                header_bytes = raw[0][1] if isinstance(raw[0], tuple) else b""
                for line in header_bytes.decode("utf-8", errors="replace").splitlines():
                    if line.lower().startswith("message-id:"):
                        ids.add(line.split(":", 1)[1].strip())
    except Exception:
        pass
    return ids


def extrair_nao_processados(conta: dict) -> list[dict]:
    """
    Conecta via IMAP, busca e-mails da INBOX que não estejam
    na pasta 'Processado' (compatível com Gmail e Outlook).
    """
    resultados = []
    conn = imaplib.IMAP4_SSL(conta["imap_server"], int(conta["imap_port"]))
    try:
        conn.login(conta["email"], conta["password"])
        _garantir_pasta(conn, PASTA_PROCESSADO)

        # Carrega IDs já processados para filtrar
        ja_processados = _ids_ja_processados(conn, PASTA_PROCESSADO)

        conn.select("INBOX")
        _, uid_data = conn.uid("SEARCH", None, "ALL")
        uids = uid_data[0].split() if uid_data[0] else []

        for uid in uids:
            try:
                _, raw = conn.uid("FETCH", uid, "(RFC822)")
                raw_bytes = raw[0][1]
                msg = email.message_from_bytes(raw_bytes)

                message_id = msg.get("Message-ID", f"<sem-id-{uid.decode()}>").strip()

                if message_id in ja_processados:
                    continue

                remetente = _decodificar_header(msg.get("From", ""))
                assunto = _decodificar_header(msg.get("Subject", "(sem assunto)"))
                corpo = _extrair_texto(msg)

                date_str = msg.get("Date", "")
                try:
                    data_recebimento = email.utils.parsedate_to_datetime(date_str)
                except Exception:
                    data_recebimento = None

                resultados.append({
                    "message_id": message_id,
                    "remetente": remetente,
                    "assunto": assunto,
                    "corpo": corpo,
                    "data_recebimento": data_recebimento,
                    "_uid": uid,
                })
            except Exception:
                continue
    finally:
        try:
            conn.logout()
        except Exception:
            pass

    return resultados


def marcar_processados(conta: dict, uids: list[bytes]):
    """Copia os e-mails para a pasta 'Processado' — funciona em Gmail e Outlook."""
    if not uids:
        return
    try:
        conn = imaplib.IMAP4_SSL(conta["imap_server"], int(conta["imap_port"]))
        conn.login(conta["email"], conta["password"])
        _garantir_pasta(conn, PASTA_PROCESSADO)
        conn.select("INBOX")
        for uid in uids:
            try:
                conn.uid("COPY", uid, PASTA_PROCESSADO)
            except Exception:
                pass
        conn.logout()
    except Exception:
        pass
