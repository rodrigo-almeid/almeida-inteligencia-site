import os
import json
import io
import uuid
import threading
from typing import Optional

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.database import get_db, SessionLocal
from backend.core.security import get_current_user
from backend.core.models import User
from backend.emails.models import ContaEmail, EmailExtraido
from backend.emails.extractor import extrair_nao_processados, marcar_processados
from backend.emails.trainer import treinar, classificar_ml, modelo_existe

router = APIRouter(prefix="/api", tags=["Emails"])

_jobs: dict = {}

FERNET_KEY = os.getenv("FERNET_SECRET_KEY")
fernet = Fernet(FERNET_KEY)

SUBCATEGORIAS = [
    "Compra de VT – Admissão",
    "Compra de VT – Extra",
    "Vínculo de carga ao cartão",
    "Gestão de saldo",
    "2ª via de cartão VT",
    "Comunicados da operadora VT",
    "Emails gerenciais – VT",
    "Compra de VR",
    "2ª via de cartão VR",
    "Recebimento de boleto",
    "Recebimento de NF",
    "Não classificado",
]

_SUBCAT_CATEGORIA = {
    "Compra de VT – Admissão":      "VT",
    "Compra de VT – Extra":         "VT",
    "Vínculo de carga ao cartão":   "VT",
    "Gestão de saldo":              "VT",
    "2ª via de cartão VT":          "VT",
    "Comunicados da operadora VT":  "VT",
    "Emails gerenciais – VT":       "VT",
    "Compra de VR":                 "VR",
    "2ª via de cartão VR":          "VR",
    "Recebimento de boleto":        "Outros",
    "Recebimento de NF":            "Outros",
    "Não classificado":             "Outros",
}
_SUBCAT_GERENCIAL = {"Emails gerenciais – VT"}


def _derivar_campos(subcategoria: str) -> tuple[str, str]:
    categoria = _SUBCAT_CATEGORIA.get(subcategoria, "Outros")
    gerencial = "sim" if subcategoria in _SUBCAT_GERENCIAL else "nao"
    return categoria, gerencial


# ── Schemas ───────────────────────────────────────────────────────────────────

class ContaEmailIn(BaseModel):
    nome: str
    provider: str = "gmail"
    email: str
    password: str
    imap_server: str = "imap.gmail.com"
    imap_port: int = 993


class ContaEmailOut(BaseModel):
    id: int
    nome: str
    provider: str
    email: str
    imap_server: str
    imap_port: int
    ativo: int


class AtualizarEmail(BaseModel):
    categoria: Optional[str] = None
    subcategoria: Optional[str] = None
    sla: Optional[str] = None
    gerencial: Optional[str] = None
    status: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log(job_id: str, tipo: str, msg: str):
    _jobs[job_id]["progresso"].append({"tipo": tipo, "msg": msg})


def _config_conta(conta: ContaEmail) -> dict:
    return {
        "email": conta.email,
        "password": fernet.decrypt(conta.password_enc.encode()).decode(),
        "imap_server": conta.imap_server,
        "imap_port": conta.imap_port,
        "provider": conta.provider,
    }


# ── Contas IMAP ───────────────────────────────────────────────────────────────

@router.get("/contas", response_model=list[ContaEmailOut])
def listar_contas(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    contas = db.query(ContaEmail).filter(ContaEmail.user_id == user.id).all()
    return [ContaEmailOut(id=c.id, nome=c.nome, provider=c.provider, email=c.email,
                          imap_server=c.imap_server, imap_port=c.imap_port, ativo=c.ativo) for c in contas]


@router.post("/contas", response_model=ContaEmailOut)
def criar_conta(payload: ContaEmailIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    password_enc = fernet.encrypt(payload.password.encode()).decode()
    conta = ContaEmail(
        user_id=user.id,
        nome=payload.nome,
        provider=payload.provider,
        email=payload.email,
        password_enc=password_enc,
        imap_server=payload.imap_server,
        imap_port=payload.imap_port,
    )
    db.add(conta)
    db.commit()
    db.refresh(conta)
    return ContaEmailOut(id=conta.id, nome=conta.nome, provider=conta.provider, email=conta.email,
                         imap_server=conta.imap_server, imap_port=conta.imap_port, ativo=conta.ativo)


@router.put("/contas/{conta_id}", response_model=ContaEmailOut)
def atualizar_conta(conta_id: int, payload: ContaEmailIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conta = db.query(ContaEmail).filter(ContaEmail.id == conta_id, ContaEmail.user_id == user.id).first()
    if not conta:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    conta.nome = payload.nome
    conta.provider = payload.provider
    conta.email = payload.email
    conta.password_enc = fernet.encrypt(payload.password.encode()).decode()
    conta.imap_server = payload.imap_server
    conta.imap_port = payload.imap_port
    db.commit()
    db.refresh(conta)
    return ContaEmailOut(id=conta.id, nome=conta.nome, provider=conta.provider, email=conta.email,
                         imap_server=conta.imap_server, imap_port=conta.imap_port, ativo=conta.ativo)


@router.patch("/contas/{conta_id}/ativo")
def toggle_conta(conta_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conta = db.query(ContaEmail).filter(ContaEmail.id == conta_id, ContaEmail.user_id == user.id).first()
    if not conta:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    conta.ativo = 0 if conta.ativo else 1
    db.commit()
    return {"ativo": conta.ativo}


@router.delete("/contas/{conta_id}", status_code=204)
def remover_conta(conta_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conta = db.query(ContaEmail).filter(ContaEmail.id == conta_id, ContaEmail.user_id == user.id).first()
    if conta:
        db.delete(conta)
        db.commit()


@router.post("/contas/{conta_id}/testar")
def testar_conta(conta_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    import imaplib
    import socket
    conta = db.query(ContaEmail).filter(ContaEmail.id == conta_id, ContaEmail.user_id == user.id).first()
    if not conta:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    try:
        password = fernet.decrypt(conta.password_enc.encode()).decode()
        mail = imaplib.IMAP4_SSL(conta.imap_server, conta.imap_port, timeout=10)
        mail.login(conta.email, password)
        mail.logout()
        return {"ok": True, "msg": "Conexão bem-sucedida!"}
    except imaplib.IMAP4.error as e:
        return {"ok": False, "msg": f"Autenticação falhou: {e}"}
    except (socket.gaierror, OSError) as e:
        return {"ok": False, "msg": f"Erro de rede: {e}"}
    except Exception as e:
        return {"ok": False, "msg": f"Erro: {e}"}


# ── Dataset / Modelo / Treinamento ────────────────────────────────────────────

@router.get("/subcategorias")
def listar_subcategorias(_: User = Depends(get_current_user)):
    return SUBCATEGORIAS


@router.get("/exportar-dataset")
def exportar_dataset(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    registros = db.query(EmailExtraido).filter(EmailExtraido.user_id == user.id).order_by(EmailExtraido.data_recebimento.desc()).all()
    dataset = [
        {"id": r.id, "assunto": r.assunto, "corpo": r.corpo or "", "remetente": r.remetente,
         "data_recebimento": r.data_recebimento.isoformat() if r.data_recebimento else None,
         "categoria": r.categoria, "subcategoria": r.subcategoria, "sla": r.sla,
         "gerencial": r.gerencial, "status": r.status}
        for r in registros
    ]
    conteudo = json.dumps(dataset, ensure_ascii=False, indent=2)
    return StreamingResponse(
        io.BytesIO(conteudo.encode("utf-8")),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=dataset_emails.json"},
    )


@router.get("/modelo-status")
def status_modelo(user: User = Depends(get_current_user)):
    return modelo_existe(user.id)


@router.post("/treinar")
def treinar_modelo(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"status": "desabilitado", "msg": "ML desabilitado temporariamente. Reative scikit-learn no requirements.txt."}


@router.get("/pendentes")
def contar_pendentes(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    total = db.query(EmailExtraido).filter(
        EmailExtraido.user_id == user.id, EmailExtraido.status == "novo"
    ).count()
    return {"pendentes": total}


# ── Job status ────────────────────────────────────────────────────────────────

@router.get("/job/{job_id}")
def status_job(job_id: str, _: User = Depends(get_current_user)):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return job


# ── Extração ──────────────────────────────────────────────────────────────────

def _executar_extracao(job_id: str, contas: list[dict], user_id: int):
    db = SessionLocal()
    try:
        total_novos = total_dup = total_restantes = 0

        for conta_cfg in contas:
            nome_conta = conta_cfg["nome"]
            _log(job_id, "info", f"[{nome_conta}] Conectando ao IMAP ({conta_cfg['imap_server']})…")
            try:
                mensagens, restantes = extrair_nao_processados(conta_cfg)
            except Exception as exc:
                _log(job_id, "erro", f"[{nome_conta}] Falha na conexão: {exc}")
                continue

            total_restantes += restantes
            total = len(mensagens)
            if total == 0:
                _log(job_id, "ok", f"[{nome_conta}] Nenhum e-mail novo.")
                continue

            _log(job_id, "info", f"[{nome_conta}] {total} e-mail(s) neste lote{f' (+{restantes} aguardando)' if restantes else ''}.")
            uids_salvos = []

            for idx, m in enumerate(mensagens, 1):
                assunto_curto = (m["assunto"] or "(sem assunto)")[:55]
                existe = db.query(EmailExtraido).filter(EmailExtraido.message_id == m["message_id"]).first()
                if existe:
                    total_dup += 1
                    _log(job_id, "aviso", f"[{nome_conta}] [{idx}/{total}] Duplicado: {assunto_curto}")
                    continue

                _log(job_id, "import", f"[{nome_conta}] [{idx}/{total}] Importando: {assunto_curto}")
                dt = m.get("data_recebimento")
                registro = EmailExtraido(
                    message_id=m["message_id"],
                    conta_id=conta_cfg.get("conta_id"),
                    user_id=user_id,
                    remetente=m["remetente"],
                    assunto=m["assunto"],
                    corpo=m["corpo"],
                    data_recebimento=dt.replace(tzinfo=None) if dt else None,
                    status="novo",
                )
                db.add(registro)
                total_novos += 1
                if m.get("_uid"):
                    uids_salvos.append(m["_uid"])

            db.commit()
            if uids_salvos:
                _log(job_id, "info", f"[{nome_conta}] Marcando {len(uids_salvos)} e-mail(s) como Processado…")
                marcar_processados(conta_cfg, uids_salvos)

        msg_final = f"Lote concluído — {total_novos} importado(s), {total_dup} duplicado(s)."
        if total_restantes:
            msg_final += f" Ainda restam ~{total_restantes} e-mail(s). Clique em Extrair novamente."
        _log(job_id, "ok", msg_final)
        _jobs[job_id].update({"status": "concluido", "resultado": {"extraidos": total_novos, "ignorados_duplicados": total_dup, "restantes": total_restantes}})
    except Exception as exc:
        db.rollback()
        _log(job_id, "erro", f"Erro: {exc}")
        _jobs[job_id].update({"status": "erro", "erro": str(exc)})
    finally:
        db.close()


@router.post("/extrair")
def extrair_emails(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    contas = db.query(ContaEmail).filter(ContaEmail.user_id == user.id, ContaEmail.ativo == 1).all()
    if not contas:
        raise HTTPException(status_code=400, detail="Nenhuma conta de e-mail ativa configurada")

    contas_cfg = [{**_config_conta(c), "nome": c.nome, "conta_id": c.id} for c in contas]
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "pendente", "progresso": [], "tipo": "extracao"}
    threading.Thread(target=_executar_extracao, args=(job_id, contas_cfg, user.id), daemon=True).start()
    return {"job_id": job_id}


# ── Classificação ─────────────────────────────────────────────────────────────

def _executar_classificacao(job_id: str, user_id: int):
    db = SessionLocal()
    try:
        registros = db.query(EmailExtraido).filter(
            EmailExtraido.user_id == user_id, EmailExtraido.status == "novo"
        ).all()

        total = len(registros)
        if total == 0:
            _log(job_id, "ok", "Nenhum e-mail pendente para classificar.")
            _jobs[job_id].update({"status": "concluido", "resultado": {"classificados": 0, "nao_classificados": 0}})
            return

        _log(job_id, "info", f"{total} e-mail(s) aguardando classificação.")
        classificados = nao_classificados = 0

        for idx, r in enumerate(registros, 1):
            assunto_curto = (r.assunto or "(sem assunto)")[:55]
            ml = classificar_ml(r.assunto, r.corpo or "", user_id)

            if ml["subcategoria"]:
                categoria, gerencial = _derivar_campos(ml["subcategoria"])
                r.subcategoria = ml["subcategoria"]
                r.categoria = categoria
                r.gerencial = gerencial
                r.sla = ml["sla"]
                r.status = "classificado"
                classificados += 1
                conf = ml.get("confianca_subcategoria")
                conf_str = f" ({conf*100:.0f}%)" if conf else ""
                _log(job_id, "ia", f"[{idx}/{total}] IA → {ml['subcategoria']} ({ml['sla'] or '—'}){conf_str}: {assunto_curto}")
            else:
                r.subcategoria = "Não classificado"
                r.categoria = "Outros"
                r.gerencial = "nao"
                r.status = "nao_classificado"
                nao_classificados += 1
                _log(job_id, "aviso", f"[{idx}/{total}] Confiança insuficiente: {assunto_curto}")

        db.commit()
        _log(job_id, "ok", f"Concluído — {classificados} classificado(s), {nao_classificados} sem classificação.")
        _jobs[job_id].update({"status": "concluido", "resultado": {"classificados": classificados, "nao_classificados": nao_classificados}})
    except Exception as exc:
        db.rollback()
        _log(job_id, "erro", f"Erro: {exc}")
        _jobs[job_id].update({"status": "erro", "erro": str(exc)})
    finally:
        db.close()


@router.post("/classificar")
def classificar_emails(user: User = Depends(get_current_user)):
    return {"status": "desabilitado", "msg": "ML desabilitado temporariamente. Reative scikit-learn no requirements.txt."}


# ── Listagem ──────────────────────────────────────────────────────────────────

@router.get("/emails")
def listar_emails(
    page: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    categoria: Optional[str] = None,
    subcategoria: Optional[str] = None,
    sla: Optional[str] = None,
    gerencial: Optional[str] = None,
    status: Optional[str] = None,
    conta_id: Optional[int] = None,
    busca: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(EmailExtraido).filter(EmailExtraido.user_id == user.id)
    if categoria:     q = q.filter(EmailExtraido.categoria == categoria)
    if subcategoria:  q = q.filter(EmailExtraido.subcategoria == subcategoria)
    if sla:           q = q.filter(EmailExtraido.sla == sla)
    if gerencial:     q = q.filter(EmailExtraido.gerencial == gerencial)
    if status:        q = q.filter(EmailExtraido.status == status)
    if conta_id:      q = q.filter(EmailExtraido.conta_id == conta_id)
    if busca:
        like = f"%{busca}%"
        q = q.filter(EmailExtraido.remetente.ilike(like) | EmailExtraido.assunto.ilike(like))

    total = q.count()
    registros = q.order_by(EmailExtraido.data_recebimento.desc().nullslast()).offset((page - 1) * por_pagina).limit(por_pagina).all()

    return {
        "total": total,
        "pagina": page,
        "por_pagina": por_pagina,
        "paginas": (total + por_pagina - 1) // por_pagina,
        "items": [{
            "id": r.id, "conta_id": r.conta_id, "remetente": r.remetente, "assunto": r.assunto,
            "data_recebimento": r.data_recebimento.isoformat() if r.data_recebimento else None,
            "categoria": r.categoria, "subcategoria": r.subcategoria, "sla": r.sla,
            "gerencial": r.gerencial, "status": r.status,
        } for r in registros],
    }


@router.get("/emails/{email_id}")
def detalhe_email(email_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.query(EmailExtraido).filter(EmailExtraido.id == email_id, EmailExtraido.user_id == user.id).first()
    if not r:
        raise HTTPException(status_code=404, detail="E-mail não encontrado")
    return {"id": r.id, "conta_id": r.conta_id, "remetente": r.remetente, "assunto": r.assunto,
            "corpo": r.corpo, "data_recebimento": r.data_recebimento.isoformat() if r.data_recebimento else None,
            "categoria": r.categoria, "subcategoria": r.subcategoria, "sla": r.sla,
            "gerencial": r.gerencial, "status": r.status}


@router.put("/emails/{email_id}")
def atualizar_email(email_id: int, payload: AtualizarEmail, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.query(EmailExtraido).filter(EmailExtraido.id == email_id, EmailExtraido.user_id == user.id).first()
    if not r:
        raise HTTPException(status_code=404, detail="E-mail não encontrado")
    if payload.categoria is not None:    r.categoria = payload.categoria
    if payload.subcategoria is not None: r.subcategoria = payload.subcategoria
    if payload.sla is not None:          r.sla = payload.sla
    if payload.gerencial is not None:    r.gerencial = payload.gerencial
    if payload.status is not None:       r.status = payload.status
    db.commit()
    return {"ok": True}
