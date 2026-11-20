"""T-013: GET/PATCH /settings + validasi 02-requirements.md §3. TC-041."""

import pytest

EXPECTED_KEYS = {
    "score_weights", "score_min_threshold", "chat_delay_ms", "chat_reaction_words",
    "live_segment_seconds", "live_block_minutes", "live_last_n_default_s", "max_heavy_jobs",
    "confirm_usage_over_min", "max_audio_minutes_per_job", "transcriber_provider",
    "llm_provider", "llm_models", "kick_live_chat_enabled", "upload_default_mode",
    "upload_platforms_enabled", "caption_templates", "manual_upload_urls",
    "default_subtitle_style", "output_dir", "download_max_height", "secrets", "storage",
}


def error(resp):
    assert resp.status_code == 400, resp.text
    return resp.json()["error"]


def test_get_has_every_key_like_api_example(api):
    body = api.get("/api/v1/settings").json()
    assert set(body) == EXPECTED_KEYS
    assert body["score_weights"] == {"audio": 0.3, "chat": 0.2, "llm": 0.5}
    assert body["kick_live_chat_enabled"] is False
    assert body["max_heavy_jobs"] == 1


def test_tc041_weights_total_must_be_100(api):
    err = error(api.patch("/api/v1/settings",
                          json={"score_weights": {"audio": 0.3, "chat": 0.3, "llm": 0.5}}))
    assert err == {"code": "VALIDATION_ERROR", "message": "Total bobot harus 100%.",
                   "fields": {"score_weights": "Total bobot harus 100%."}}
    assert api.get("/api/v1/settings").json()["score_weights"]["chat"] == 0.2  # tidak berubah


def test_weights_within_tolerance_saved(api):
    resp = api.patch("/api/v1/settings",
                     json={"score_weights": {"audio": 0.3333, "chat": 0.3333, "llm": 0.3334}})
    assert resp.status_code == 200
    assert resp.json()["score_weights"]["llm"] == 0.3334


def test_patch_saves_and_returns_full_settings(api):
    resp = api.patch("/api/v1/settings", json={
        "chat_delay_ms": 12000, "max_heavy_jobs": 2, "chat_reaction_words": [" wkwk ", "gg"],
        "llm_models": {"judge_highlight": "model-a", "translate_lines": None,
                       "write_captions": None},
        "default_subtitle_style": "Sederhana", "kick_live_chat_enabled": True,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == EXPECTED_KEYS
    assert body["chat_delay_ms"] == 12000
    assert body["chat_reaction_words"] == ["wkwk", "gg"]
    assert body["llm_models"]["judge_highlight"] == "model-a"
    assert api.get("/api/v1/settings").json()["default_subtitle_style"] == "Sederhana"


@pytest.mark.parametrize(("payload", "field", "message"), [
    ({"chat_delay_ms": 30001}, "chat_delay_ms", "Jeda chat harus 0–30 detik."),
    ({"chat_delay_ms": -1}, "chat_delay_ms", "Jeda chat harus 0–30 detik."),
    ({"live_last_n_default_s": 10}, "live_last_n_default_s", "Pilih durasi antara 15 dan 90 detik."),
    ({"default_subtitle_style": "Tidak Ada"}, "default_subtitle_style",
     "Gaya Subtitle tidak ditemukan."),
])
def test_rule_messages(api, payload, field, message):
    err = error(api.patch("/api/v1/settings", json=payload))
    assert err["fields"] == {field: message}
    assert err["message"] == message


@pytest.mark.parametrize("payload", [
    {"score_weights": {"audio": 1.2, "chat": -0.2, "llm": 0}},
    {"score_weights": {"audio": 0.5, "chat": 0.5}},
    {"score_min_threshold": 101},
    {"max_heavy_jobs": 0},
    {"transcriber_provider": "whisper"},
    {"upload_platforms_enabled": ["youtube", "twitter"]},
    {"manual_upload_urls": {"tiktok": "http://tiktok.com/upload"}},
    {"output_dir": "   "},
    {"secrets": {}},            # bagian baca-saja
    {"kunci_asing": 1},
    {"score_min_threshold": None},
])
def test_invalid_patch_rejected(api, payload):
    assert error(api.patch("/api/v1/settings", json=payload))["code"] == "VALIDATION_ERROR"


def test_output_dir_absolute_kept(api, tmp_path):
    target = str(tmp_path / "hasil")
    assert api.patch("/api/v1/settings", json={"output_dir": target}).json()[
        "output_dir"] == target
