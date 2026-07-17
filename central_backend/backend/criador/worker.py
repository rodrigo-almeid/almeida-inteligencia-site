"""
ARQ worker — executa download + transcrição em background.
Rodar: arq backend.criador.worker.WorkerSettings
"""
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from backend.core.database import SessionLocal
from backend.criador.models import TranscricaoJob

MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "/app/media/transcricoes"))
MAX_DURACAO_SEGUNDOS = 14_400  # 4 horas


def _db() -> Session:
    return SessionLocal()


def _atualiza(db: Session, job: TranscricaoJob, **kwargs):
    for k, v in kwargs.items():
        setattr(job, k, v)
    job.atualizado_em = datetime.utcnow()
    db.commit()


async def transcrever_video(ctx, job_id: str):
    db = _db()
    job: TranscricaoJob = db.query(TranscricaoJob).filter_by(id=job_id).first()
    if not job:
        return

    tmp_dir = tempfile.mkdtemp(prefix="criador_")
    try:
        # ── 1. Download ──────────────────────────────────────────────────
        _atualiza(db, job, status="baixando")

        import yt_dlp

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": f"{tmp_dir}/%(id)s.%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
            }],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(job.url, download=True)

        video_id = info.get("id", "unknown")
        canal = info.get("channel") or info.get("uploader") or "desconhecido"
        titulo_video = info.get("title") or video_id
        duracao = float(info.get("duration") or 0)

        if duracao > MAX_DURACAO_SEGUNDOS:
            raise ValueError(f"Vídeo muito longo: {duracao:.0f}s (máximo {MAX_DURACAO_SEGUNDOS}s)")

        audio_path = Path(tmp_dir) / f"{video_id}.wav"
        if not audio_path.exists():
            candidates = list(Path(tmp_dir).glob("*.wav"))
            if not candidates:
                raise FileNotFoundError("Arquivo de áudio não encontrado após download")
            audio_path = candidates[0]

        # ── 2. Transcrição ────────────────────────────────────────────────
        _atualiza(db, job, status="transcrevendo", video_id=video_id,
                  canal=canal, titulo_video=titulo_video, duracao_segundos=duracao)

        from faster_whisper import WhisperModel

        device = os.getenv("WHISPER_DEVICE", "cpu")
        compute_type = "int8" if device == "cpu" else "float16"

        model = WhisperModel(job.model_size, device=device, compute_type=compute_type)
        segments_raw, _ = model.transcribe(str(audio_path), language=job.idioma or None)

        segmentos = [
            {"inicio": round(s.start, 2), "fim": round(s.end, 2), "texto": s.text.strip()}
            for s in segments_raw
        ]

        # ── 3. Salva arquivos ─────────────────────────────────────────────
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)

        txt_path = MEDIA_DIR / f"{video_id}.txt"
        srt_path = MEDIA_DIR / f"{video_id}.srt"

        with open(txt_path, "w", encoding="utf-8") as f:
            for seg in segmentos:
                f.write(seg["texto"] + "\n")

        with open(srt_path, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segmentos, 1):
                f.write(f"{i}\n")
                f.write(f"{_fmt_srt(seg['inicio'])} --> {_fmt_srt(seg['fim'])}\n")
                f.write(seg["texto"] + "\n\n")

        # ── 4. Persiste resultado ────────────────────────────────────────
        _atualiza(
            db, job,
            status="concluido",
            segmentos_json=json.dumps(segmentos, ensure_ascii=False),
            arquivo_txt_url=f"/media/transcricoes/{video_id}.txt",
            arquivo_srt_url=f"/media/transcricoes/{video_id}.srt",
        )

        # ── 5. Webhook opcional ──────────────────────────────────────────
        if job.webhook_url:
            await _dispara_webhook(job)

    except Exception as exc:
        _atualiza(db, job, status="erro", erro=str(exc))
        if job.webhook_url:
            await _dispara_webhook(job)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        db.close()


async def _dispara_webhook(job: TranscricaoJob):
    payload = {"job_id": job.id, "status": job.status, "erro": job.erro}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(job.webhook_url, json=payload)
    except Exception:
        pass


def _fmt_srt(segundos: float) -> str:
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = int(segundos % 60)
    ms = int((segundos - int(segundos)) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


from arq.connections import RedisSettings as _RedisSettings


class WorkerSettings:
    functions = [transcrever_video]
    redis_settings = _RedisSettings(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", "6379")),
    )
