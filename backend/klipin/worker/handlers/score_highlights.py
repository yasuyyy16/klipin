"""Job `score_highlights` (FR-009 s.d. FR-012): sinyal → pra-seleksi → LLM → Kandidat Klip `auto`.

1. Jendela 60/30 detik di rentang yang ditranskripsi. Bila `highlight_windows` sudah ada
   (hitung ulang/coba ulang), sinyal & pra-seleksi tersimpan dipakai ulang tanpa dekode audio.
2. LLM hanya untuk jendela terpilih yang belum `done` (cache INT-05); hasil disimpan per jendela.
   LLM tidak tersedia → skor parsial dari Audio + Chat (log Job), bukan gagal.
3. Skor tiap jendela dengan bobot Pengaturan (BR-001/BR-002), kandidat dipilih (BR-004–006).
4. Klip `auto` berstatus `candidate` diganti; Klip yang sudah direview, `live_marker`, dan
   `manual` tidak disentuh dan rentangnya dihindari (BR-005).
"""

import json
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import Connection, Engine, text

from klipin import app_settings
from klipin.clips import clock, defaults
from klipin.db.models import utcnow
from klipin.highlight import audio_signal, candidates, chat_signal, preselect
from klipin.highlight.scoring import Weights, combine
from klipin.providers.llm import HighlightJudge, JudgeUnavailable, get_judge, judge_all
from klipin.providers.llm.base import JudgeResult, WindowInput
from klipin.worker.context import JobContext
from klipin.worker.handlers import register

CONTEXT_MS = 15_000  # transkrip jendela 60 dtk + 15 dtk di kiri-kanan ≈ "±90 detik" (INT-05)
MSG_NO_SOURCE = "Video sumber tidak tersedia, Sinyal Audio tidak bisa dihitung."
REVIEWED = ("approved", "rejected", "rendering", "rendered", "render_failed")


def transcribed_range(conn: Connection, stream_id: int, duration_ms: int) -> tuple[int, int]:
    """Rentang Job `transcribe` seluruh stream terakhir yang sukses (rentang konfirmasi FR-022)."""
    raw = conn.execute(text(
        "SELECT checkpoint FROM jobs WHERE source_stream_id = :s AND job_type = 'transcribe' "
        "AND scope_start_ms IS NULL AND status = 'succeeded' ORDER BY id DESC LIMIT 1"),
        {"s": stream_id}).scalar()
    chosen = (json.loads(raw) if raw else {}).get("range") or {}
    start = max(0, int(chosen.get("start_ms", 0)))
    end = min(duration_ms, int(chosen.get("end_ms", duration_ms)))
    return (start, end) if end > start else (0, duration_ms)


def _load_windows(conn: Connection, stream_id: int) -> list[preselect.Window]:
    rows = conn.execute(text(
        "SELECT start_ms, end_ms, audio_signal, chat_signal, preselected FROM highlight_windows "
        "WHERE source_stream_id = :s ORDER BY start_ms"), {"s": stream_id}).all()
    return [preselect.Window(a, b, au, ch, bool(p)) for a, b, au, ch, p in rows]


def _transcript(conn: Connection, stream_id: int, w: preselect.Window) -> list[str]:
    rows = conn.execute(text(
        "SELECT start_ms, speaker, text FROM transcript_segments WHERE source_stream_id = :s "
        "AND end_ms >= :a AND start_ms <= :b ORDER BY start_ms"),
        {"s": stream_id, "a": w.start_ms - CONTEXT_MS, "b": w.end_ms + CONTEXT_MS}).all()
    return [f"[{(t - w.start_ms) / 1000:.1f}] {sp or '?'}: {tx}" for t, sp, tx in rows]


def _store_llm(engine: Engine, stream_id: int, w: WindowInput, r: JudgeResult) -> None:
    j = r.judgement
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE highlight_windows SET llm_status = :st, llm_score = :sc, llm_category = :c, "
            "llm_reason = :re, llm_suggested_start_ms = :a, llm_suggested_end_ms = :b, "
            "llm_suggested_title = :t, updated_at = :now "
            "WHERE source_stream_id = :s AND start_ms = :k"),
            {"st": r.status, "sc": j.score if j else None, "c": j.category if j else None,
             "re": j.reason[:200] if j else None,
             "a": w.start_ms + round(j.suggested_start_s * 1000) if j else None,
             "b": w.start_ms + round(j.suggested_end_s * 1000) if j else None,
             "t": j.title[:100] if j else None, "now": utcnow(), "s": stream_id,
             "k": w.start_ms})


def _judge(ctx: JobContext, windows: list[preselect.Window],
           factory: Callable[[Engine], HighlightJudge]) -> None:
    with ctx.engine.connect() as conn:
        done = {r[0] for r in conn.execute(text(
            "SELECT start_ms FROM highlight_windows WHERE source_stream_id = :s "
            "AND llm_status = 'done'"), {"s": ctx.source_stream_id})}
        language = conn.execute(text("SELECT detected_language FROM source_streams WHERE id = :s"),
                                {"s": ctx.source_stream_id}).scalar()
        todo = [WindowInput(w.start_ms, w.start_ms, w.end_ms, language,
                            _transcript(conn, ctx.source_stream_id, w), w.audio, w.chat)
                for w in windows if w.preselected and w.start_ms not in done]
    ctx.log(f"LLM: {len(todo)} jendela dinilai, {len(done)} dari cache")
    if not todo:
        return
    try:
        judge = factory(ctx.engine)
    except JudgeUnavailable as e:
        ctx.log(f"{e} {e.detail}".strip())
        return
    finished = 0

    def on_result(w: WindowInput, r: JudgeResult) -> None:
        nonlocal finished
        _store_llm(ctx.engine, ctx.source_stream_id, w, r)
        finished += 1
        ctx.progress(20 + finished * 70 // len(todo), f"Menilai jendela {finished}/{len(todo)}")

    try:
        judge_all(judge, todo, should_cancel=ctx.cancel_event.is_set, on_result=on_result)
    except JudgeUnavailable as e:
        ctx.log(f"{e} {e.detail}".strip())


def _replace_clips(ctx: JobContext, chosen: list[candidates.Candidate], preset: int,
                   style: int, name: str) -> None:
    with ctx.engine.begin() as conn:
        conn.execute(text("DELETE FROM clips WHERE source_stream_id = :s AND origin = 'auto' "
                          "AND status = 'candidate'"), {"s": ctx.source_stream_id})
        for c in chosen:
            row = c.source.payload
            conn.execute(text(
                "INSERT INTO clips (source_stream_id, origin, status, start_ms, end_ms, score, "
                "score_audio, score_chat, score_llm, score_partial, category, reason, title, "
                "layout_preset_id, subtitle_style_id) VALUES (:s, 'auto', 'candidate', :a, :b, "
                ":score, :au, :ch, :llm, :p, :cat, :re, :t, :preset, :style)"),
                {"s": ctx.source_stream_id, "a": c.start_ms, "b": c.end_ms, "score": c.source.score,
                 "au": row["audio"], "ch": row["chat"], "llm": row["llm"],
                 "p": int(c.source.partial), "cat": row["category"], "re": row["reason"],
                 "t": row["title"] or f"{name} - {clock(c.start_ms)}"[:100],
                 "preset": preset, "style": style})


def run(ctx: JobContext, *, judge_factory: Callable[[Engine], HighlightJudge] | None = None) -> int:
    sid = ctx.source_stream_id
    with ctx.engine.connect() as conn:
        video, duration, deleted = conn.execute(text(
            "SELECT video_path, duration_ms, source_deleted_at FROM source_streams WHERE id = :s"),
            {"s": sid}).one()
        weights = Weights.from_setting(app_settings.value(conn, "score_weights"))
        threshold = int(app_settings.value(conn, "score_min_threshold", 40))
        bounds = transcribed_range(conn, sid, duration or 0)
        windows = _load_windows(conn, sid)

    if windows:
        ctx.log(f"memakai {len(windows)} jendela tersimpan (sinyal & pra-seleksi)")
    else:
        if not video or deleted or not Path(video).is_file():
            raise RuntimeError(MSG_NO_SOURCE)
        ctx.progress(2, "Menghitung Sinyal Audio")
        audio = audio_signal.spike_signal(audio_signal.loudness_db_per_second(
            Path(video), should_cancel=ctx.cancel_event.is_set))
        ctx.progress(15, "Menghitung Sinyal Chat")
        with ctx.engine.begin() as conn:
            chat = chat_signal.stream_chat_signal(conn, sid, duration or 0)
            windows = preselect.build_windows(bounds[0], bounds[1], audio, chat)
            preselect.preselect(windows, bounds[1] - bounds[0], seed=sid)
            preselect.store(conn, sid, windows)
        ctx.log(f"{len(windows)} jendela, {sum(w.preselected for w in windows)} lolos pra-seleksi"
                + ("" if chat is not None else "; Sinyal Chat tidak tersedia"))
    ctx.progress(20, "Menilai jendela dengan LLM")
    _judge(ctx, windows, judge_factory or get_judge)

    ctx.progress(92, "Memilih Kandidat Klip")
    with ctx.engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT start_ms, end_ms, audio_signal, chat_signal, llm_status, llm_score, "
            "llm_category, llm_reason, llm_suggested_start_ms, llm_suggested_end_ms, "
            "llm_suggested_title FROM highlight_windows WHERE source_stream_id = :s"),
            {"s": sid}).all()
        occupied = [tuple(r) for r in conn.execute(text(
            "SELECT start_ms, end_ms FROM clips WHERE source_stream_id = :s AND origin = 'auto' "
            "AND status IN (" + ",".join(f"'{st}'" for st in REVIEWED) + ")"), {"s": sid})]
        preset, style, name = defaults(conn, sid)
    scored = []
    for a, b, au, ch, st, llm, cat, reason, sa, sb, title in rows:
        done = st == "done"
        score = combine(au, ch, llm if done else None, weights)
        scored.append(candidates.Scored(
            a, b, score.value, score.partial,
            (sa - a) / 1000 if done and sa is not None else None,
            (sb - a) / 1000 if done and sb is not None else None,
            {"audio": au, "chat": ch, "llm": llm if done else None,
             "category": cat if done else None, "reason": reason if done else None,
             "title": title if done else None}))
    chosen = candidates.select(scored, bounds, bounds[1] - bounds[0], threshold, occupied)
    _replace_clips(ctx, chosen, preset, style, name)
    ctx.log(f"{len(chosen)} Kandidat Klip (ambang skor {threshold})")
    ctx.progress(100, "Selesai")
    return len(chosen)


@register("score_highlights")
def handle(ctx: JobContext) -> None:
    run(ctx)
