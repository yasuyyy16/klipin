"""Job `transcribe` (FR-005, INT-04): audio → potongan → penyedia → Segmen & Kata Transkrip.

- Potongan 10 menit, tumpang tindih 2 detik: potongan i = [b_i, b_i + 10 mnt + 2 dtk],
  b_i = awal + i × 10 mnt. Satu baris `transcription_chunks` per potongan; status `done`
  adalah checkpoint (coba ulang tidak mengirim ulang potongan yang sudah selesai).
- Penjahitan: batas antar potongan = titik tengah zona tumpang tindih (b_i + 1 dtk). Kata
  dengan `start_ms` ≥ batas diambil dari potongan berikutnya, selain itu dari sebelumnya.
- Bahasa: dideteksi penyedia pada potongan pertama yang berisi kata, lalu dipakai eksplisit.
- Pembicara: label lokal per potongan → S1, S2, … dengan mencocokkan kata di zona tumpang
  tindih terhadap kata tersimpan; yang tidak cocok mendapat label baru.
- Retry 429/5xx/timeout: 3× dengan backoff 2/4/8 detik + jitter; hanya potongan itu.
- `scope_start_ms`/`scope_end_ms` membatasi rentang (Penanda Live); `checkpoint.range` berisi
  rentang pilihan Pengguna saat konfirmasi pemakaian (FR-022) dan tetap dianggap Job seluruh stream.
"""

import random
import subprocess
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection, Engine, text

from klipin.db.models import utcnow
from klipin.media import probe
from klipin.providers.transcriber import (
    AudioChunk,
    Transcriber,
    TranscriberError,
    TranscriberTransientError,
    TranscriptionResult,
    get_transcriber,
)
from klipin.worker.context import JobContext
from klipin.worker.handlers import register
from klipin.worker.handlers.download import stream_dir
from klipin.worker.process import JobCancelled

CHUNK_MS = 600_000
OVERLAP_MS = 2_000
BACKOFF_S = (2.0, 4.0, 8.0)
JITTER_S = 0.5
MATCH_TOLERANCE_MS = 300
MSG_NO_SOURCE = "Video sumber tidak tersedia, transkripsi tidak bisa dilakukan."
MSG_EXTRACT = "Gagal mengekstrak audio dari video sumber."


@dataclass(frozen=True)
class PlannedChunk:
    index: int
    start_ms: int
    end_ms: int
    own_start: int  # kata dengan start_ms di [own_start, own_end) milik potongan ini
    own_end: int


def plan_chunks(start_ms: int, end_ms: int) -> list[PlannedChunk]:
    bounds: list[tuple[int, int]] = []
    b = start_ms
    while True:
        end = min(b + CHUNK_MS + OVERLAP_MS, end_ms)
        bounds.append((b, end))
        if end >= end_ms:
            break
        b += CHUNK_MS
    half = OVERLAP_MS // 2
    plan = []
    for i, (s, e) in enumerate(bounds):
        own_start = start_ms if i == 0 else s + half
        own_end = bounds[i + 1][0] + half if i + 1 < len(bounds) else end_ms + 1
        plan.append(PlannedChunk(i, s, e, own_start, own_end))
    return plan


def _ensure_chunks(engine: Engine, stream_id: int, plan: list[PlannedChunk]) -> dict[int, dict]:
    with engine.begin() as conn:
        for pc in plan:
            conn.execute(text(
                "INSERT INTO transcription_chunks (source_stream_id, chunk_index, start_ms, end_ms)"
                " VALUES (:s, :i, :a, :b) ON CONFLICT (source_stream_id, start_ms) DO UPDATE SET "
                "chunk_index = excluded.chunk_index, end_ms = excluded.end_ms, updated_at = :now "
                "WHERE transcription_chunks.status <> 'done'"),
                {"s": stream_id, "i": pc.index, "a": pc.start_ms, "b": pc.end_ms, "now": utcnow()})
        rows = conn.execute(text(
            "SELECT id, start_ms, status FROM transcription_chunks WHERE source_stream_id = :s"),
            {"s": stream_id}).mappings().all()
    return {r["start_ms"]: dict(r) for r in rows}


def _extract(ctx: JobContext, video: Path, pc: PlannedChunk, audio_dir: Path) -> Path:
    audio_dir.mkdir(parents=True, exist_ok=True)
    out = audio_dir / f"chunk_{pc.start_ms:010d}.flac"
    err_log = audio_dir / "ffmpeg.log"
    with err_log.open("wb") as err:
        code = ctx.run([probe.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", f"{pc.start_ms / 1000:.3f}", "-t",
                        f"{(pc.end_ms - pc.start_ms) / 1000:.3f}", "-i", str(video),
                        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "flac", str(out)],
                       stdout=subprocess.DEVNULL, stderr=err)
    if code != 0 or not out.is_file():
        ctx.log(f"ffmpeg: {err_log.read_text(errors='replace')[-500:]}")
        raise RuntimeError(MSG_EXTRACT)
    return out


def _set_chunk(engine: Engine, chunk_id: int, **cols) -> None:
    sets = ", ".join(f"{k} = :{k}" for k in cols)
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE transcription_chunks SET {sets}, updated_at = :now "
                          "WHERE id = :id"), {**cols, "now": utcnow(), "id": chunk_id})


def _send(ctx: JobContext, transcriber: Transcriber, chunk: AudioChunk,
          chunk_id: int) -> TranscriptionResult:
    for attempt in range(len(BACKOFF_S) + 1):
        with ctx.engine.begin() as conn:
            conn.execute(text("UPDATE transcription_chunks SET attempts = attempts + 1 "
                              "WHERE id = :id"), {"id": chunk_id})
        try:
            return transcriber.transcribe(chunk, should_cancel=ctx.cancel_event.is_set)
        except TranscriberTransientError as e:
            if attempt == len(BACKOFF_S):
                ctx.log(f"potongan {chunk.index + 1}: {e.detail}; batas percobaan habis")
                _set_chunk(ctx.engine, chunk_id, status="failed")
                raise
            delay = BACKOFF_S[attempt] + random.uniform(0, JITTER_S if BACKOFF_S[attempt] else 0)
            ctx.log(f"potongan {chunk.index + 1}: {e.detail}; coba lagi dalam {delay:.1f} dtk")
            if ctx.cancel_event.wait(delay):
                raise JobCancelled from None
        except TranscriberError as e:
            ctx.log(f"potongan {chunk.index + 1}: {getattr(e, 'detail', '') or e}")
            _set_chunk(ctx.engine, chunk_id, status="failed")
            raise
    raise AssertionError("tidak tercapai")


def _speaker_map(conn: Connection, stream_id: int, chunk_id: int, pc: PlannedChunk,
                 words: list[tuple[int, str, str | None]]) -> dict[str, str]:
    """Label lokal → S1/S2/… lewat kata yang sama di zona tumpang tindih (±300 ms)."""
    stored = conn.execute(text(
        "SELECT w.start_ms, lower(w.word), s.speaker FROM transcript_words w "
        "JOIN transcript_segments s ON s.id = w.segment_id WHERE w.source_stream_id = :s "
        "AND s.chunk_id <> :c AND s.speaker IS NOT NULL AND w.start_ms >= :lo AND w.start_ms < :hi"),
        {"s": stream_id, "c": chunk_id, "lo": pc.start_ms - MATCH_TOLERANCE_MS,
         "hi": pc.start_ms + OVERLAP_MS + MATCH_TOLERANCE_MS}).all()
    votes: dict[str, Counter] = defaultdict(Counter)
    for start, word, local in words:
        if local is None or start >= pc.start_ms + OVERLAP_MS:
            continue
        for s_start, s_word, s_speaker in stored:
            if s_word == word.lower() and abs(s_start - start) <= MATCH_TOLERANCE_MS:
                votes[local][s_speaker] += 1
    mapping = {local: c.most_common(1)[0][0] for local, c in votes.items()}

    used = conn.execute(text(
        "SELECT DISTINCT speaker FROM transcript_segments WHERE source_stream_id = :s "
        "AND chunk_id <> :c AND speaker LIKE 'S%'"), {"s": stream_id, "c": chunk_id}).scalars()
    n = max((int(s[1:]) for s in used if s[1:].isdigit()), default=0)
    for _, _, local in words:
        if local is not None and local not in mapping:
            n += 1
            mapping[local] = f"S{n}"
    return mapping


def _store(engine: Engine, stream_id: int, chunk_id: int, pc: PlannedChunk,
           result: TranscriptionResult, provider: str, audio: Path) -> int:
    """Simpan kata milik potongan ini (setelah dijahit) dalam satu transaksi."""
    utterances = []
    for u in result.utterances:
        kept = [w for w in u.words if pc.own_start <= w.start_ms + pc.start_ms < pc.own_end]
        if kept:
            utterances.append((u, kept))
    all_words = [(w.start_ms + pc.start_ms, w.word, w.speaker or u.speaker)
                 for u in result.utterances for w in u.words]
    count = 0
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM transcript_segments WHERE chunk_id = :c"), {"c": chunk_id})
        mapping = _speaker_map(conn, stream_id, chunk_id, pc, all_words)
        for u, kept in utterances:
            local = u.speaker or kept[0].speaker
            seg_id = conn.execute(text(
                "INSERT INTO transcript_segments (source_stream_id, chunk_id, start_ms, end_ms, "
                "speaker, language, text) VALUES (:s, :c, :a, :b, :sp, :l, :t) RETURNING id"),
                {"s": stream_id, "c": chunk_id, "a": max(0, kept[0].start_ms + pc.start_ms),
                 "b": max(0, kept[-1].end_ms + pc.start_ms),
                 "sp": mapping.get(local) if local is not None else None,
                 "l": result.language, "t": " ".join(w.word for w in kept)}).scalar()
            conn.execute(text(
                "INSERT INTO transcript_words (source_stream_id, segment_id, start_ms, end_ms, "
                "word, confidence) VALUES (:s, :g, :a, :b, :w, :c)"),
                [{"s": stream_id, "g": seg_id, "a": max(0, w.start_ms + pc.start_ms),
                  "b": max(0, w.start_ms + pc.start_ms, w.end_ms + pc.start_ms), "w": w.word,
                  "c": None if w.confidence is None else min(1.0, max(0.0, w.confidence))}
                 for w in kept])
            count += len(kept)
        conn.execute(text(
            "UPDATE transcription_chunks SET status = 'done', provider = :p, audio_path = :a, "
            "updated_at = :now WHERE id = :id"),
            {"p": provider, "a": str(audio), "now": utcnow(), "id": chunk_id})
    return count


def run(ctx: JobContext, *,
        transcriber_factory: Callable[[Engine], Transcriber] | None = None) -> None:
    stream_id = ctx.source_stream_id
    # API key dicek dulu: tanpa key tidak ada audio yang diekstrak/dikirim (TC-014).
    transcriber = (transcriber_factory or get_transcriber)(ctx.engine)
    with ctx.engine.connect() as conn:
        video, duration, language, deleted = conn.execute(text(
            "SELECT video_path, duration_ms, detected_language, source_deleted_at "
            "FROM source_streams WHERE id = :s"), {"s": stream_id}).one()
    if not video or deleted or not Path(video).is_file():
        raise RuntimeError(MSG_NO_SOURCE)
    video_path = Path(video)
    total = duration or probe.duration_ms(video_path)
    # Rentang: scope Job (Penanda Live) atau rentang pilihan saat konfirmasi (FR-022).
    chosen = ctx.checkpoint.get("range") or {}
    start = max(0, ctx.scope_start_ms or chosen.get("start_ms") or 0)
    end = min(ctx.scope_end_ms or chosen.get("end_ms") or total, total)
    plan = plan_chunks(start, end)
    rows = _ensure_chunks(ctx.engine, stream_id, plan)
    audio_dir = stream_dir(stream_id) / "audio"

    done = sum(rows[pc.start_ms]["status"] == "done" for pc in plan)
    if done:
        ctx.log(f"{done}/{len(plan)} potongan sudah selesai, dilewati")
    for pc in plan:
        row = rows[pc.start_ms]
        if row["status"] == "done":
            continue
        label = f"potongan {pc.index + 1}/{len(plan)}"
        ctx.progress(pc.index * 100 // len(plan), f"Mengekstrak audio {label}")
        audio = _extract(ctx, video_path, pc, audio_dir)
        ctx.progress((pc.index * 100 + 30) // len(plan), f"Transkripsi {label}")
        result = _send(ctx, transcriber,
                       AudioChunk(audio, pc.index, pc.start_ms, pc.end_ms, language), row["id"])
        words = _store(ctx.engine, stream_id, row["id"], pc, result, transcriber.name, audio)
        if language is None and words and result.language:
            language = result.language
            with ctx.engine.begin() as conn:
                conn.execute(text("UPDATE source_streams SET detected_language = :l, "
                                  "updated_at = :now WHERE id = :s"),
                             {"l": language, "now": utcnow(), "s": stream_id})
        ctx.log(f"{label}: {words} kata")
        done += 1
        ctx.save_checkpoint({**ctx.checkpoint, "chunks_done": done, "chunks_total": len(plan)})
    ctx.progress(100, "Selesai")


@register("transcribe")
def handle(ctx: JobContext) -> None:
    run(ctx)
