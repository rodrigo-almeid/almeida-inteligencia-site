import json
import os
import re
import uuid
from pathlib import Path

import httpx
from arq.connections import RedisSettings, create_pool
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.security import get_current_user
from backend.core.models import User
from backend.criador.models import TranscricaoJob
from backend.criador.schemas import TranscricaoCreate, TranscricaoJobOut, Segmento

router = APIRouter(prefix="/api/transcricoes", tags=["criador"])

_REDIS_SETTINGS = RedisSettings(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", 6379)),
)

MODELOS_PERMITIDOS = {"tiny", "base", "small", "medium", "large-v3"}

_PROMPT_GEMINI = """\
Você é um editor de vídeo especialista em crescimento de canais no YouTube e TikTok/Reels/Shorts.

Receberá a transcrição completa de um vídeo (podcast, entrevista ou aula) com timestamps precisos.
Sua tarefa é analisar o conteúdo e sugerir dois tipos de cortes:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIPO 1 — CORTES PARA YOUTUBE (vídeos longos)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Duração ideal: entre 4 e 12 minutos
- Objetivo: momentos com narrativa completa, argumento forte ou história envolvente
- Critérios de seleção:
  • Início com gancho (pergunta, afirmação provocativa, história)
  • Desenvolvimento claro no meio
  • Conclusão satisfatória ou cliffhanger
  • Funciona como vídeo independente (quem não viu o original entende)
- Sugira de 2 a 5 cortes por transcrição

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIPO 2 — CORTES PARA TIKTOK / SHORTS / REELS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Duração ideal: entre 30 e 90 segundos (nunca passe de 3 minutos)
- Objetivo: momentos de alto impacto que param o scroll
- Critérios de seleção:
  • Começa com frase que gera curiosidade ou choque nos primeiros 3 segundos
  • Uma única ideia forte, sem divagações
  • Frases curtas, ritmo acelerado, emoção visível
  • Funciona sem contexto — o espectador entende tudo sozinho
  • Preferência por: opiniões fortes, revelações, humor, estatísticas surpreendentes, histórias pessoais
- Sugira de 5 a 10 cortes por transcrição

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORMATO DE RESPOSTA (JSON puro, sem markdown)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "cortes_youtube": [
    {
      "titulo": "título chamativo para o vídeo no YouTube",
      "inicio": 123.4,
      "fim": 834.1,
      "duracao_segundos": 710.7,
      "gancho": "frase de abertura que aparece nos primeiros 5 segundos do corte",
      "descricao": "resumo em 2 frases do que acontece nesse trecho e por que prende atenção",
      "tags_youtube": ["tag1", "tag2", "tag3"]
    }
  ],
  "cortes_tiktok": [
    {
      "titulo": "legenda curta para o TikTok (max 100 caracteres)",
      "inicio": 45.0,
      "fim": 112.3,
      "duracao_segundos": 67.3,
      "gancho": "exatamente o que é dito nos primeiros 3 segundos",
      "descricao": "por que esse momento para o scroll",
      "hashtags": ["#hashtag1", "#hashtag2"]
    }
  ]
}

Responda APENAS com o JSON. Nenhum texto antes ou depois.
"""


async def _enqueue(job_id: str):
    redis = await create_pool(_REDIS_SETTINGS)
    await redis.enqueue_job("transcrever_video", job_id)
    await redis.aclose()


def _nome_arquivo(canal: str, titulo: str) -> str:
    def limpa(s: str) -> str:
        s = s.strip()
        s = re.sub(r'[\\/*?:"<>|]', "", s)
        return s[:80]
    return f"{limpa(canal)} - {limpa(titulo)}.json"


@router.post("", status_code=202)
async def criar_transcricao(
    payload: TranscricaoCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.model_size not in MODELOS_PERMITIDOS:
        raise HTTPException(400, f"model_size inválido. Use: {MODELOS_PERMITIDOS}")

    job_ativo = (
        db.query(TranscricaoJob)
        .filter(
            TranscricaoJob.user_id == current_user.id,
            TranscricaoJob.status.in_(["pendente", "baixando", "transcrevendo"]),
        )
        .first()
    )
    if job_ativo:
        raise HTTPException(429, "Você já tem uma transcrição em andamento. Aguarde terminar.")

    job = TranscricaoJob(
        id=str(uuid.uuid4()),
        url=payload.url,
        idioma=payload.idioma,
        model_size=payload.model_size,
        webhook_url=payload.webhook_url,
        user_id=current_user.id,
    )
    db.add(job)
    db.commit()

    await _enqueue(job.id)

    return {"job_id": job.id, "status": "pendente"}


@router.get("/{job_id}/status")
def status_transcricao(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job: TranscricaoJob = db.query(TranscricaoJob).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(404, "Job não encontrado")
    if job.user_id != current_user.id:
        raise HTTPException(403, "Acesso negado")
    return {"job_id": job.id, "status": job.status}


@router.get("/{job_id}/gemini")
def payload_gemini(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna payload pronto para enviar à API do Gemini."""
    job: TranscricaoJob = db.query(TranscricaoJob).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(404, "Job não encontrado")
    if job.user_id != current_user.id:
        raise HTTPException(403, "Acesso negado")
    if job.status != "concluido":
        raise HTTPException(400, f"Transcrição ainda não concluída (status: {job.status})")

    segmentos = json.loads(job.segmentos_json)
    linhas = [f"[{s['inicio']:.1f}s → {s['fim']:.1f}s] {s['texto']}" for s in segmentos]
    conteudo_usuario = (
        f"Vídeo ID: {job.video_id}\n"
        f"Canal: {job.canal or 'desconhecido'}\n"
        f"Título: {job.titulo_video or job.video_id}\n"
        f"Duração total: {job.duracao_segundos:.0f}s ({job.duracao_segundos / 60:.1f} min)\n\n"
        f"TRANSCRIÇÃO:\n" + "\n".join(linhas)
    )

    return {
        "model": "gemini-1.5-pro",
        "system_instruction": {"parts": [{"text": _PROMPT_GEMINI}]},
        "contents": [{"role": "user", "parts": [{"text": conteudo_usuario}]}],
        "generation_config": {"temperature": 0.4, "response_mime_type": "application/json"},
        "_meta": {
            "job_id": job_id,
            "video_id": job.video_id,
            "canal": job.canal,
            "titulo_video": job.titulo_video,
            "duracao_segundos": job.duracao_segundos,
            "total_segmentos": len(segmentos),
        },
    }


@router.post("/{job_id}/sugestoes", status_code=200)
async def gerar_sugestoes(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Chama o Gemini e persiste o JSON de cortes sugeridos em disco."""
    job: TranscricaoJob = db.query(TranscricaoJob).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(404, "Job não encontrado")
    if job.user_id != current_user.id:
        raise HTTPException(403, "Acesso negado")
    if job.status != "concluido":
        raise HTTPException(400, f"Transcrição ainda não concluída (status: {job.status})")

    if job.sugestoes_json:
        return {
            "job_id": job_id,
            "canal": job.canal,
            "titulo_video": job.titulo_video,
            "arquivo_sugestoes_url": job.arquivo_sugestoes_url,
            "sugestoes": json.loads(job.sugestoes_json),
        }

    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        raise HTTPException(500, "GEMINI_API_KEY não configurada no servidor")

    segmentos = json.loads(job.segmentos_json)
    linhas = [f"[{s['inicio']:.1f}s → {s['fim']:.1f}s] {s['texto']}" for s in segmentos]
    conteudo_usuario = (
        f"Vídeo ID: {job.video_id}\n"
        f"Canal: {job.canal or 'desconhecido'}\n"
        f"Título: {job.titulo_video or job.video_id}\n"
        f"Duração total: {job.duracao_segundos:.0f}s ({job.duracao_segundos / 60:.1f} min)\n\n"
        f"TRANSCRIÇÃO:\n" + "\n".join(linhas)
    )

    gemini_payload = {
        "system_instruction": {"parts": [{"text": _PROMPT_GEMINI}]},
        "contents": [{"role": "user", "parts": [{"text": conteudo_usuario}]}],
        "generation_config": {"temperature": 0.4, "response_mime_type": "application/json"},
    }

    url_gemini = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-1.5-pro:generateContent?key={gemini_api_key}"
    )

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url_gemini, json=gemini_payload)

    if resp.status_code != 200:
        raise HTTPException(502, f"Gemini retornou erro {resp.status_code}: {resp.text[:300]}")

    texto_resposta = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    sugestoes = json.loads(texto_resposta)

    media_dir = Path(os.getenv("MEDIA_DIR", "/app/media/transcricoes"))
    media_dir.mkdir(parents=True, exist_ok=True)

    nome = _nome_arquivo(job.canal or "desconhecido", job.titulo_video or job.video_id)
    caminho = media_dir / nome
    caminho.write_text(json.dumps(sugestoes, ensure_ascii=False, indent=2), encoding="utf-8")

    url_relativa = f"/media/transcricoes/{nome}"

    from datetime import datetime
    job.sugestoes_json = json.dumps(sugestoes, ensure_ascii=False)
    job.arquivo_sugestoes_url = url_relativa
    job.atualizado_em = datetime.utcnow()
    db.commit()

    return {
        "job_id": job_id,
        "canal": job.canal,
        "titulo_video": job.titulo_video,
        "arquivo_sugestoes_url": url_relativa,
        "sugestoes": sugestoes,
    }


@router.get("/{job_id}/sugestoes")
def obter_sugestoes(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recupera sugestões já geradas sem chamar o Gemini novamente."""
    job: TranscricaoJob = db.query(TranscricaoJob).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(404, "Job não encontrado")
    if job.user_id != current_user.id:
        raise HTTPException(403, "Acesso negado")
    if not job.sugestoes_json:
        raise HTTPException(404, "Sugestões ainda não geradas. Use POST /sugestoes primeiro.")

    return {
        "job_id": job_id,
        "canal": job.canal,
        "titulo_video": job.titulo_video,
        "arquivo_sugestoes_url": job.arquivo_sugestoes_url,
        "sugestoes": json.loads(job.sugestoes_json),
    }


@router.get("/{job_id}", response_model=TranscricaoJobOut)
def obter_transcricao(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job: TranscricaoJob = db.query(TranscricaoJob).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(404, "Job não encontrado")
    if job.user_id != current_user.id:
        raise HTTPException(403, "Acesso negado")

    segmentos = None
    if job.segmentos_json:
        raw = json.loads(job.segmentos_json)
        segmentos = [Segmento(**s) for s in raw]

    return TranscricaoJobOut(
        job_id=job.id,
        status=job.status,
        canal=job.canal,
        titulo_video=job.titulo_video,
        video_id=job.video_id,
        duracao_segundos=job.duracao_segundos,
        segmentos=segmentos,
        arquivo_txt_url=job.arquivo_txt_url,
        arquivo_srt_url=job.arquivo_srt_url,
        arquivo_sugestoes_url=job.arquivo_sugestoes_url,
        erro=job.erro,
    )


@router.get("", response_model=list[TranscricaoJobOut])
def listar_transcricoes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    jobs = (
        db.query(TranscricaoJob)
        .filter_by(user_id=current_user.id)
        .order_by(TranscricaoJob.criado_em.desc())
        .limit(50)
        .all()
    )
    result = []
    for job in jobs:
        segmentos = None
        if job.segmentos_json:
            raw = json.loads(job.segmentos_json)
            segmentos = [Segmento(**s) for s in raw]
        result.append(TranscricaoJobOut(
            job_id=job.id,
            status=job.status,
            canal=job.canal,
            titulo_video=job.titulo_video,
            video_id=job.video_id,
            duracao_segundos=job.duracao_segundos,
            segmentos=segmentos,
            arquivo_txt_url=job.arquivo_txt_url,
            arquivo_srt_url=job.arquivo_srt_url,
            arquivo_sugestoes_url=job.arquivo_sugestoes_url,
            erro=job.erro,
        ))
    return result
