"""Speech -> (policy | RAG + LLM) -> speech orchestration."""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from .config import Settings, load_settings
from .incidents import IncidentStore
from .llm import as_messages, make_llm
from .locales.lt.normalize import Lexicon, LithuanianNormalizer
from .policy import Policy
from .rag import KnowledgeBase, PlaceIndex
from .rag.places import SOURCE_TITLE as SHELTER_TITLE, SOURCE_URL as SHELTER_URL
from .speech import make_stt, make_tts
from .speech.base import STTResult, TTSResult

LOCALES_DIR = Path(__file__).resolve().parent / "locales"


@dataclass
class Citation:
    n: int
    title: str
    url: str
    publisher: str = ""


@dataclass
class Answer:
    text: str
    action: str  # answer | no_info | emergency_transfer | operator_transfer | language_transfer | repeat
    language: str = "lt"
    citations: list[Citation] = field(default_factory=list)
    spoken_text: str = ""
    speaking_rate: float = 1.0
    llm: str = ""
    latency_ms: dict = field(default_factory=dict)
    retrieval: list[dict] = field(default_factory=list)
    place: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Session:
    last_answer: Answer | None = None
    slow: bool = False
    turns: list[dict] = field(default_factory=list)


@dataclass
class TurnResult:
    answer: Answer
    transcript: STTResult | None = None
    audio: TTSResult | None = None

    def to_dict(self) -> dict:
        d = {"answer": self.answer.to_dict()}
        if self.transcript:
            d["transcript"] = {k: v for k, v in asdict(self.transcript).items() if k != "raw"}
        if self.audio:
            d["audio"] = {"provider": self.audio.provider, "voice": self.audio.voice, "mime": self.audio.mime,
                          "latency_ms": round(self.audio.latency_ms, 1), "bytes": len(self.audio.audio)}
        return d


class KnowledgeLine:
    def __init__(self, settings: Settings | None = None, llm_provider: str | None = None,
                 stt_provider: str | None = None, tts_provider: str | None = None, llm_model: str | None = None):
        self.settings = settings or load_settings()
        s = self.settings
        self.profile = s.profile
        pdir = s.profile_dir
        self.messages = self.profile.get("messages", {})
        self.policy_cfg = self.profile.get("policy", {})
        self.policy = Policy(self.policy_cfg)
        self.kb = KnowledgeBase.from_dir(pdir / self.profile.get("kb_dir", "kb"))
        self.places = PlaceIndex.from_csv(pdir / self.profile.get("shelters_csv", "data/shelters.csv"))
        inc = Path(self.profile.get("incidents_file", "data/incidents.json"))
        self.incidents = IncidentStore(inc if inc.is_absolute() else pdir / inc)
        prompts_file = LOCALES_DIR / s.lang / "prompts.yaml"
        self.prompts = yaml.safe_load(prompts_file.read_text(encoding="utf-8"))
        self.normalizer = LithuanianNormalizer(Lexicon.load()) if s.lang == "lt" else None
        self.llm_name, self.llm_model, self.llm = make_llm(s, llm_provider, llm_model)
        self._stt_req, self._tts_req = stt_provider, tts_provider
        self._stt = self._tts = None

    # -- lazy speech providers ------------------------------------------------
    @property
    def stt(self):
        if self._stt is None:
            self._stt = make_stt(self.settings, self._stt_req)
        return self._stt

    @property
    def tts(self):
        if self._tts is None:
            self._tts = make_tts(self.settings, self._tts_req)
        return self._tts

    # -- text helpers ---------------------------------------------------------
    @property
    def service_name(self) -> str:
        return self.profile.get("service_name", "informacijos liniją")

    def greeting(self) -> str:
        g = " ".join(self.messages.get("greeting", "").split()).format(service_name=self.service_name)
        active = self.incidents.active()
        if active:
            pre = self.messages.get("active_incident_prefix", "")
            note = " ".join(f"{i['title']} ({i.get('area', '')}). {i.get('message', '')}" for i in active)
            g = g.replace("Kuo galiu padėti?", f"{pre}{note} Kuo galiu padėti?")
        return g

    def speakable(self, text: str) -> str:
        t = re.sub(r"\s*\[\d+(?:,\s*\d+)*\]", "", text)
        if self.normalizer and self.settings.get("tts.normalize", True):
            t = self.normalizer(t)
        return t

    def _msg(self, key: str, **kw) -> str:
        return " ".join(str(self.messages.get(key, "")).split()).format(**kw)

    # -- core -----------------------------------------------------------------
    def answer(self, question: str, session: Session | None = None) -> Answer:
        session = session or Session()
        t0 = time.perf_counter()
        intent = self.policy.classify(question, has_previous_answer=session.last_answer is not None)
        rate = float(self.settings.get("tts.speaking_rate", 1.0))
        slow_rate = float(self.settings.get("tts.slow_speaking_rate", 0.8))

        if intent.kind == "language":
            msgs = self.messages.get("unsupported_language", {})
            ans = Answer(text=" ".join(msgs.get(intent.language, msgs.get("en", "")).split()),
                         action="language_transfer", language=intent.language)
        elif intent.kind == "emergency":
            ans = Answer(text=self._msg("emergency"), action="emergency_transfer")
        elif intent.kind == "human":
            ans = Answer(text=self._msg("human"), action="operator_transfer")
        elif intent.kind == "slower":
            prev = session.last_answer
            session.slow = True
            ans = Answer(text=self._msg("repeat_slower_prefix") + " " + prev.text, action="repeat",
                         citations=prev.citations, speaking_rate=slow_rate)
        elif intent.kind == "simpler":
            ans = self._simplify(session.last_answer)
        else:
            ans = self._rag_answer(question)

        if session.slow and ans.language == "lt":
            ans.speaking_rate = slow_rate
        elif ans.speaking_rate == 1.0:
            ans.speaking_rate = rate
        ans.spoken_text = self.speakable(ans.text) if ans.language == "lt" else ans.text
        ans.latency_ms["total_text"] = round((time.perf_counter() - t0) * 1000, 1)
        if ans.action not in ("repeat",):
            session.last_answer = ans
        session.turns.append({"q": question, "a": ans.text, "action": ans.action})
        return ans

    def _simplify(self, prev: Answer) -> Answer:
        t0 = time.perf_counter()
        prompt = self.prompts["simplify"].format(previous=prev.text)
        system = self.prompts["system"].format(service_name=self.service_name)
        try:
            out = self.llm.invoke(as_messages(system, prompt))
            text = _content(out) if self.llm_name != "mock" else prev.text
        except Exception:
            text = prev.text
        return Answer(text=text, action="answer", citations=prev.citations, llm=f"{self.llm_name}:{self.llm_model}",
                      latency_ms={"llm": round((time.perf_counter() - t0) * 1000, 1)})

    def _expand(self, question: str) -> str:
        extra = [v for pat, v in (self.profile.get("query_expansions") or {}).items()
                 if re.search(pat, question, flags=re.I)]
        return question + (" " + " ".join(extra) if extra else "")

    def _rag_answer(self, question: str) -> Answer:
        lat: dict = {}
        t0 = time.perf_counter()
        k = int(self.settings.get("rag.top_k", 4))
        hits = self.kb.search(self._expand(question), k=k)
        lat["retrieval"] = round((time.perf_counter() - t0) * 1000, 1)
        min_score = float(self.settings.get("rag.min_score", 2.0))

        blocks: list[tuple[str, str, str, str]] = []  # (title, url, publisher, text)
        place = None
        prefix = ""
        if self.policy.is_shelter_question(question) and len(self.places):
            m = self.places.match(question, municipality_hint=self.profile.get("default_municipality") or None)
            if m and m.shelters:
                place = {"eldership": m.eldership, "municipality": m.municipality,
                         "shelters": [s.describe() for s in m.shelters]}
                listing = "; ".join(f"{i + 1}) {s.describe()}" for i, s in enumerate(m.shelters))
                blocks.append((SHELTER_TITLE, SHELTER_URL, "PAGD",
                               f"Priedangos {m.eldership} seniūnijoje ({m.municipality}): {listing}."))
                prefix = self._msg("confirm_place", eldership=m.eldership.replace(" sen.", ""),
                                   municipality=m.municipality)
        for inc in self.incidents.active():
            blocks.append((f"Aktyvus incidentas: {inc['title']}", "", inc.get("source", ""),
                           f"{inc['title']} ({inc.get('area', '')}): {inc.get('message', '')}"))
        min_overlap = float(self.settings.get("rag.min_overlap", 0.34))
        good = [h for h in hits if h.score >= min_score and h.overlap >= min_overlap]
        budget = int(self.settings.get("rag.max_context_chars", 6000))
        for h in good:
            if sum(len(b[3]) for b in blocks) > budget:
                break
            blocks.append((h.chunk.title, h.chunk.url, h.chunk.publisher, h.chunk.text))
        retrieval = [{"id": h.chunk.id, "score": round(h.score, 2), "overlap": round(h.overlap, 2), "title": h.chunk.title}
                     for h in hits]

        if not good and not place:
            return Answer(text=self._msg("no_info"), action="no_info", retrieval=retrieval, latency_ms=lat)

        context = "\n".join(
            f'<šaltinis nr="{i + 1}" pavadinimas="{t}">\n{txt}\n</šaltinis>' for i, (t, _u, _p, txt) in enumerate(blocks)
        )
        extra = "Skambinančiojo vieta atpažinta – paminėk 1–2 artimiausias priedangas iš šaltinio.\n" if place else ""
        user = self.prompts["user"].format(context=context, question=question, extra=extra)
        system = self.prompts["system"].format(service_name=self.service_name)
        t1 = time.perf_counter()
        try:
            out = self.llm.invoke(as_messages(system, user))
            text = _content(out).strip()
        except Exception as e:  # provider failure -> safe fallback, never silence
            text = self._msg("no_info")
            lat["llm_error"] = f"{type(e).__name__}: {str(e)[:200]}"
        lat["llm"] = round((time.perf_counter() - t1) * 1000, 1)
        used = sorted({int(n) for n in re.findall(r"\[(\d+)\]", text)} or {1})
        cites = [Citation(n=n, title=blocks[n - 1][0], url=blocks[n - 1][1], publisher=blocks[n - 1][2])
                 for n in used if 0 < n <= len(blocks) and blocks[n - 1][1]]
        return Answer(text=(prefix.strip() + " " + text) if prefix else text, action="answer", citations=cites, llm=f"{self.llm_name}:{self.llm_model}",
                      latency_ms=lat, retrieval=retrieval, place=place)

    # -- speech turns -----------------------------------------------------------
    def speak(self, answer: Answer) -> TTSResult:
        lang = "lt-LT" if answer.language == "lt" else {"ru": "ru-RU", "uk": "uk-UA", "en": "en-GB", "pl": "pl-PL"}[answer.language]
        res = self.tts.synthesize(answer.spoken_text or answer.text, language=lang, speaking_rate=answer.speaking_rate)
        answer.latency_ms["tts"] = round(res.latency_ms, 1)
        return res

    def turn_text(self, question: str, session: Session | None = None, with_audio: bool = True) -> TurnResult:
        ans = self.answer(question, session)
        audio = self.speak(ans) if with_audio else None
        return TurnResult(answer=ans, audio=audio)

    def turn_audio(self, audio: bytes, mime: str = "audio/wav", session: Session | None = None,
                   with_audio: bool = True) -> TurnResult:
        tr = self.stt.transcribe(audio, mime=mime, language=self.settings.locale)
        ans = self.answer(tr.text, session)
        ans.latency_ms["stt"] = round(tr.latency_ms, 1)
        out = self.speak(ans) if with_audio else None
        return TurnResult(answer=ans, transcript=tr, audio=out)

    def describe(self) -> dict:
        def name(get):
            try:
                return get().name
            except Exception as e:
                return f"unavailable ({type(e).__name__})"

        return {"llm": f"{self.llm_name}:{self.llm_model}", "stt": name(lambda: self.stt), "tts": name(lambda: self.tts),
                "kb_chunks": len(self.kb.chunks), "shelters": len(self.places), "locale": self.settings.locale,
                "profile": self.profile.get("name")}


def _content(msg) -> str:
    c = getattr(msg, "content", msg)
    if isinstance(c, list):  # Gemini may return content parts
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in c)
    return str(c)
