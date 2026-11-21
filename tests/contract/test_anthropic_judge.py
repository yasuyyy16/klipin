"""T-038: HighlightJudge — adapter Anthropic (kontrak HTTP lewat MockTransport), FakeJudge,
pemilihan penyedia, penilaian paralel. TC-023. Tanpa panggilan API berbayar."""

import json
import threading
import time
from pathlib import Path

import anthropic
import httpx2
import pytest

from klipin import secrets
from klipin.config import get_config
from klipin.providers import llm
from klipin.providers.llm import anthropic_judge as aj
from klipin.providers.llm.base import MSG_NO_KEY, MSG_NO_MODEL, WindowInput
from klipin.worker.process import JobCancelled

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "providers"
KEY = "sk-uji-anthropic-123"
WINDOW = WindowInput(key=7, start_ms=600_000, end_ms=660_000, language="id",
                     transcript=["[3.0] S1: eh itu apa di belakang", "[5.5] S2: gila kaget banget"],
                     audio_signal=0.91, chat_signal=0.84, layout_preset="gaming")


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"anthropic_{name}.json").read_text(encoding="utf-8"))


class Server:
    """Antrean respons palsu untuk POST /v1/messages; mencatat setiap request."""

    def __init__(self, *responses: tuple[int, dict]) -> None:
        self.queue = list(responses)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        status, body = self.queue.pop(0) if len(self.queue) > 1 else self.queue[0]
        return httpx2.Response(status, json=body)

    def bodies(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests]


def judge_for(server: Server, sleeps: list | None = None) -> aj.AnthropicJudge:
    client = anthropic.Anthropic(
        api_key=KEY, max_retries=0,
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(server)))
    return aj.AnthropicJudge(KEY, "model-uji", client=client,
                             sleep=(sleeps.append if sleeps is not None else lambda s: None))


def test_success_request_shape_and_parsed_result():
    server = Server((200, fixture("judge_success")))
    result = judge_for(server).judge(WINDOW)
    assert result.status == "done" and result.attempts == 1
    j = result.judgement
    assert (j.score, j.category, j.suggested_start_s, j.suggested_end_s) == (82, "hype", 12.4, 56.0)
    assert j.title == "Jumpscare paling brutal"

    req = server.requests[0]
    assert req.url.path == "/v1/messages"
    assert req.headers["authorization"] == f"Bearer {KEY}"  # cara SDK anthropic 2.x
    body = server.bodies()[0]
    assert body["model"] == "model-uji"  # dari Pengaturan, bukan hardcode
    assert body["max_tokens"] == 300
    assert body["output_config"]["effort"] == "low"
    schema = body["output_config"]["format"]["schema"]
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert set(schema["required"]) == {"score", "category", "reason", "suggested_start_s",
                                       "suggested_end_s", "title"}
    assert schema["additionalProperties"] is False
    user = body["messages"][0]["content"]
    assert "Sinyal Audio: 0.91; Sinyal Chat: 0.84" in user
    assert "[5.5] S2: gila kaget banget" in user and "Durasi jendela: 60 detik" in user
    assert "Preset Layout: gaming" in user
    assert "S1/S2" in user and "≥ 70" in body["system"]


def test_tc023_invalid_twice_then_marked_invalid():
    server = Server((200, fixture("judge_invalid")), (200, fixture("judge_invalid")))
    result = judge_for(server).judge(WINDOW)
    assert (result.status, result.judgement, result.attempts) == ("invalid", None, 2)
    assert len(server.requests) == 2  # coba ulang tepat 1×


def test_invalid_once_then_valid():
    server = Server((200, fixture("judge_invalid")), (200, fixture("judge_success")))
    result = judge_for(server).judge(WINDOW)
    assert (result.status, result.attempts) == ("done", 2)


@pytest.mark.parametrize("patch", [
    {"content": [{"type": "text", "text": json.dumps({
        "score": 150, "category": "hype", "reason": "x", "suggested_start_s": 1,
        "suggested_end_s": 20, "title": "t"})}]},
    {"content": [{"type": "text", "text": json.dumps({
        "score": 50, "category": "seru", "reason": "x", "suggested_start_s": 1,
        "suggested_end_s": 20, "title": "t"})}]},
    {"stop_reason": "max_tokens"},
])
def test_out_of_schema_or_truncated_is_invalid(patch):
    bad = {**fixture("judge_success"), **patch}
    result = judge_for(Server((200, bad))).judge(WINDOW)
    assert result.status == "invalid"


def test_refusal_is_failed_not_retried():
    refusal = {**fixture("judge_success"), "stop_reason": "refusal", "content": []}
    server = Server((200, refusal))
    result = judge_for(server).judge(WINDOW)
    assert (result.status, result.detail) == ("failed", "refusal")
    assert len(server.requests) == 1


def test_429_retried_with_backoff_then_success():
    sleeps: list[float] = []
    server = Server((429, fixture("429")), (429, fixture("429")), (200, fixture("judge_success")))
    result = judge_for(server, sleeps).judge(WINDOW)
    assert result.status == "done"
    assert len(server.requests) == 3
    assert 2.0 <= sleeps[0] <= 2.5 and 4.0 <= sleeps[1] <= 4.5


def test_overloaded_exhausted_is_failed():
    sleeps: list[float] = []
    server = Server((529, fixture("529")))
    result = judge_for(server, sleeps).judge(WINDOW)
    assert result.status == "failed"
    assert len(server.requests) == 4 and len(sleeps) == 3  # 1 + 3 coba ulang (2/4/8 dtk)


@pytest.mark.parametrize(("status", "name"), [(401, "401"), (404, "404")])
def test_auth_or_model_error_makes_judge_unavailable(status, name):
    with pytest.raises(llm.JudgeUnavailable) as e:
        judge_for(Server((status, fixture(name)))).judge(WINDOW)
    assert "Skor memakai Sinyal Audio dan Chat saja" in str(e.value)
    assert KEY not in e.value.detail


def test_cancel_before_request():
    server = Server((200, fixture("judge_success")))
    with pytest.raises(JobCancelled):
        judge_for(server).judge(WINDOW, should_cancel=lambda: True)
    assert server.requests == []


def test_prompt_never_contains_chat_authors_and_is_trimmed():
    long = WindowInput(1, 0, 60_000, "id", [f"[{i}.0] S1: " + "kata " * 50 for i in range(200)],
                       0.1, None)
    prompt = aj.build_prompt(long)
    assert prompt.endswith("[dipangkas]") and len(prompt) < aj.TRANSCRIPT_MAX_CHARS + 400
    assert "Sinyal Chat: tidak tersedia" in prompt


# --- pemilihan penyedia -------------------------------------------------------------------

def test_get_judge(engine, home, memory_keyring, monkeypatch):
    with pytest.raises(llm.JudgeUnavailable) as e:
        llm.get_judge(engine)
    assert str(e.value) == MSG_NO_KEY
    secrets.set_secret("llm_api_key", KEY)
    assert isinstance(llm.get_judge(engine), llm.FakeJudge)

    monkeypatch.setenv("KLIPIN_PROVIDERS", "real")
    get_config.cache_clear()
    with pytest.raises(llm.JudgeUnavailable) as e:  # seed: llm_models.judge_highlight = null
        llm.get_judge(engine)
    assert str(e.value) == MSG_NO_MODEL
    with engine.begin() as conn:
        conn.exec_driver_sql("""UPDATE settings SET value = '{"judge_highlight": "model-uji",
            "translate_lines": null, "write_captions": null}' WHERE key = 'llm_models'""")
    judge = llm.get_judge(engine)
    assert isinstance(judge, aj.AnthropicJudge) and judge.model == "model-uji"


# --- FakeJudge & paralel ------------------------------------------------------------------

def windows(n: int) -> list[WindowInput]:
    return [WindowInput(i, i * 30_000, i * 30_000 + 60_000, "id", [], i / n, None)
            for i in range(n)]


def test_fake_judge_deterministic_and_tc023():
    fake = llm.FakeJudge(invalid_times={3: 2}, fail={5})
    results = llm.judge_all(fake, windows(10))
    assert results[3].status == "invalid" and results[3].attempts == 2
    assert results[5].status == "failed"
    assert results[9].status == "done" and results[9].judgement.score == 90
    assert results[9].judgement.category == "hype"
    assert fake.calls.count(3) == 2
    again = llm.judge_all(llm.FakeJudge(), windows(10))
    assert again[9].judgement == results[9].judgement


def test_judge_all_runs_at_most_4_in_parallel():
    active, peak, lock = 0, 0, threading.Lock()

    class Slow(llm.FakeJudge):
        def judge(self, window, *, should_cancel=None):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return super().judge(window)

    seen = []
    results = llm.judge_all(Slow(), windows(12), on_result=lambda w, r: seen.append(w.key))
    assert len(results) == 12 and sorted(seen) == list(range(12))
    assert peak == 4


def test_judge_all_propagates_unavailable():
    class Broken(llm.FakeJudge):
        def judge(self, window, *, should_cancel=None):
            raise llm.JudgeUnavailable("mati")

    with pytest.raises(llm.JudgeUnavailable):
        llm.judge_all(Broken(), windows(5))


def test_secret_test_endpoint_uses_anthropic_in_real_mode(api, memory_keyring, monkeypatch):
    monkeypatch.setenv("KLIPIN_PROVIDERS", "real")
    get_config.cache_clear()
    secrets.set_secret("llm_api_key", KEY)
    calls = []
    monkeypatch.setattr(aj, "test_key", lambda value: calls.append(value))
    body = api.post("/api/v1/secrets/llm_api_key/test").json()
    assert body["ok"] is True and body["provider"] == "anthropic" and calls == [KEY]
