"""
Extrator IMAP — Gmail e Outlook/Exchange.
Busca apenas e-mails não lidos (UNSEEN) na INBOX.
Após salvar, marca como lido e copia para 'Processado'.
"""
import imaplib
import email
import email.header
import email.utils
import re

PASTA_PROCESSADO = "Processado"
LOTE_MAXIMO = 50


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
        pass


def contar_unseen(conta: dict) -> int:
    conn = imaplib.IMAP4_SSL(conta["imap_server"], int(conta["imap_port"]))
    try:
        conn.login(conta["email"], conta["password"])
        conn.select("INBOX", readonly=True)
        _, uid_data = conn.uid("SEARCH", None, "UNSEEN")
        uids = uid_data[0].split() if uid_data[0] else []
        return len(uids)
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def extrair_lote(conta: dict, offset: int = 0) -> tuple[list[dict], int, int]:
    """
    Busca UNSEEN na INBOX, pula `offset` e retorna até LOTE_MAXIMO.
    Returns: (mensagens, total_unseen, restantes_apos_lote)
    """
    resultados = []
    conn = imaplib.IMAP4_SSL(conta["imap_server"], int(conta["imap_port"]))
    try:
        conn.login(conta["email"], conta["password"])
        _garantir_pasta(conn, PASTA_PROCESSADO)
        conn.select("INBOX")

        _, uid_data = conn.uid("SEARCH", None, "UNSEEN")
        todos_uids = uid_data[0].split() if uid_data[0] else []
        total_unseen = len(todos_uids)
        uids = todos_uids[:LOTE_MAXIMO]
        restantes = max(0, total_unseen - LOTE_MAXIMO)

        for uid in uids:
            try:
                _, raw = conn.uid("FETCH", uid, "(RFC822)")
                raw_bytes = raw[0][1]
                msg = email.message_from_bytes(raw_bytes)

                message_id = msg.get("Message-ID", f"<sem-id-{uid.decode()}>").strip()
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

    return resultados, total_unseen, restantes


def marcar_processados(conta: dict, uids: list[bytes]):
    """Marca como lido e copia para 'Processado'."""
    if not uids:
        return
    try:
        conn = imaplib.IMAP4_SSL(conta["imap_server"], int(conta["imap_port"]))
        conn.login(conta["email"], conta["password"])
        _garantir_pasta(conn, PASTA_PROCESSADO)
        conn.select("INBOX")
        for uid in uids:
            try:
                conn.uid("STORE", uid, "+FLAGS", "\\Seen")
                conn.uid("COPY", uid, PASTA_PROCESSADO)
            except Exception:
                pass
        conn.logout()
    except Exception:
        pass
