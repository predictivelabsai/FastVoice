from pathlib import Path

from knowledge_line.config import load_settings
from knowledge_line.incidents import IncidentStore
from knowledge_line.speech.mock import MockTTS


def test_kb_loaded_with_sources(kl):
    assert len(kl.kb.chunks) > 20
    assert all(c.url.startswith("https://") for c in kl.kb.chunks)


def test_answer_cites_public_source(kl):
    a = kl.answer("Kada reikia skambinti 112?")
    assert a.action == "answer"
    assert any("112" in c.title or "bpc" in c.url for c in a.citations)
    assert "vienas, vienas, du" in a.spoken_text or "112" not in a.text


def test_audio_roundtrip_with_mocks(kl):
    audio = MockTTS().synthesize("Kaip atpažinti priedangą?").audio
    res = kl.turn_audio(audio, mime="audio/wav")
    assert res.transcript.text == "Kaip atpažinti priedangą?"
    assert res.answer.action == "answer"
    assert res.audio and res.audio.audio[:4] == b"RIFF"


def test_greeting_mentions_active_incident(kl, tmp_path):
    src = kl.incidents.path
    store = IncidentStore(tmp_path / "inc.json")
    store.save(IncidentStore(src).load())
    kl.incidents = store
    assert "Dėmesio" not in kl.greeting()
    store.set_status("demo-power-outage", "active")
    assert "Elektros tiekimo sutrikimas" in kl.greeting()
    kl.incidents = IncidentStore(src)


def test_env_expansion(monkeypatch):
    monkeypatch.setenv("KL_GEMINI_MODEL", "gemini-test")
    assert load_settings().get("llm.models.gemini") == "gemini-test"


def test_stub_providers_disabled_by_default():
    import pytest

    from knowledge_line.speech import ProviderNotConfigured, make_tts

    with pytest.raises(ProviderNotConfigured):
        make_tts(load_settings(), "azure")
    with pytest.raises(ProviderNotConfigured):
        make_tts(load_settings(), "tilde")


def test_eval_runs_and_scores(kl):
    from knowledge_line.evaluation import load_items, run_eval

    items = load_items(kl.settings.profile_dir / "eval" / "lt_eval.yaml")
    m = run_eval(kl, items).metrics()
    assert m["n"] == len(items) and m["action_accuracy"] >= 0.8


def test_web_routes():
    from starlette.testclient import TestClient

    from knowledge_line.web import app

    c = TestClient(app)
    assert c.get("/").status_code == 200
    r = c.post("/api/ask", json={"question": "Kas yra priedanga?", "session_id": "t"})
    assert r.status_code == 200 and r.json()["audio_data"].startswith("data:audio/wav")
    assert c.get("/admin").status_code == 200
