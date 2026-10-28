import pytest

from knowledge_line.policy import detect_language


@pytest.mark.parametrize("text,lang", [
    ("Kur man slėptis?", "lt"), ("Здравствуйте, где ближайшее укрытие?", "ru"),
    ("Де найближче укриття? Їжа є?", "uk"), ("Where is the nearest shelter, please?", "en"),
    ("Gdzie jest najbliższy schron?", "pl"), ("Labas", "lt"),
])
def test_detect_language(text, lang):
    assert detect_language(text) == lang


@pytest.mark.parametrize("q,action", [
    ("Kažkoks dūmas, sunku kvėpuoti, kaimynui bloga.", "emergency_transfer"),
    ("Žmogus be sąmonės!", "emergency_transfer"),
    ("Ar aš kalbu su žmogumi? Noriu su žmogumi.", "operator_transfer"),
    ("Здравствуйте, где ближайшее укрытие?", "language_transfer"),
    ("Kokia rytoj bus krepšinio rungtynių pradžia?", "no_info"),
    ("Kur man slėptis, jei paskelbtų oro pavojų?", "answer"),
])
def test_actions(kl, q, action):
    assert kl.answer(q).action == action


def test_slower_and_simpler_need_previous_answer(kl):
    from knowledge_line.pipeline import Session

    s = Session()
    first = kl.answer("Ką įsidėti į išvykimo krepšį?", s)
    assert first.action == "answer" and first.citations
    rep = kl.answer("Pakartokite, prašau, lėčiau.", s)
    assert rep.action == "repeat" and rep.speaking_rate < 1.0 and first.text in rep.text
    simp = kl.answer("Nesupratau...", s)
    assert simp.action == "answer"
