"""Lithuanian answer-quality and speech round-trip metrics."""

from __future__ import annotations

import re
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .locales.lt.stem import fold, stem
from .policy import detect_language

LIST_MARKUP = re.compile(r"(^\s*[-*•]\s|\*\*|#|\|)", re.M)


def _words(text: str) -> list[str]:
    return re.findall(r"[0-9a-z]+", fold(text))


def point_covered(answer: str, alternatives: list[str]) -> bool:
    toks = _words(answer)
    for alt in alternatives:
        parts = [stem(w) for w in re.findall(r"[0-9A-Za-zĄČĘĖĮŠŲŪŽąčęėįšųūžа-яА-ЯёЁ]+", alt)]
        parts = [fold(p) for p in parts]
        if parts and all(any(t.startswith(p) for t in toks) for p in parts):
            return True
        if fold(alt) in fold(answer):
            return True
    return False


def edit_distance(a: list, b: list) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def wer(ref: str, hyp: str) -> float:
    r, h = _words(ref), _words(hyp)
    return edit_distance(r, h) / max(1, len(r))


def cer(ref: str, hyp: str) -> float:
    r, h = " ".join(_words(ref)), " ".join(_words(hyp))
    return edit_distance(list(r), list(h)) / max(1, len(r))


@dataclass
class ItemResult:
    id: str
    question: str
    expected_action: str
    action: str
    answer: str
    points_total: int
    points_hit: int
    cited: bool
    lt_ok: bool
    phone_style_ok: bool
    words: int
    latency_ms: float
    error: str = ""

    @property
    def action_ok(self) -> bool:
        return self.action == self.expected_action

    @property
    def coverage(self) -> float:
        return self.points_hit / max(1, self.points_total)


@dataclass
class EvalSummary:
    provider: str
    items: list[ItemResult] = field(default_factory=list)

    def metrics(self) -> dict:
        it = self.items
        ans = [i for i in it if i.expected_action == "answer"]
        lat = [i.latency_ms for i in it if i.action == "answer" and not i.error]
        return {
            "provider": self.provider,
            "n": len(it),
            "action_accuracy": round(sum(i.action_ok for i in it) / max(1, len(it)), 3),
            "point_coverage": round(statistics.mean([i.coverage for i in it]) if it else 0, 3),
            "answer_point_coverage": round(statistics.mean([i.coverage for i in ans]) if ans else 0, 3),
            "citation_rate": round(sum(i.cited for i in ans) / max(1, len(ans)), 3),
            "lithuanian_rate": round(sum(i.lt_ok for i in ans) / max(1, len(ans)), 3),
            "phone_style_rate": round(sum(i.phone_style_ok for i in ans) / max(1, len(ans)), 3),
            "avg_words": round(statistics.mean([i.words for i in ans]) if ans else 0, 1),
            "latency_p50_ms": round(statistics.median(lat), 0) if lat else None,
            "latency_p95_ms": round(sorted(lat)[max(0, int(len(lat) * 0.95) - 1)], 0) if lat else None,
            "errors": sum(bool(i.error) for i in it),
        }


def load_items(path: Path | str) -> list[dict]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))["items"]


def run_eval(kl, items: list[dict], label: str | None = None) -> EvalSummary:
    from .pipeline import Session

    summary = EvalSummary(provider=label or f"{kl.llm_name}:{kl.llm_model}")
    for item in items:
        t0 = time.perf_counter()
        err = ""
        try:
            a = kl.answer(item["question"], Session())
            text, action, cited = a.text, a.action, bool(a.citations)
            if a.latency_ms.get("llm_error"):
                err = a.latency_ms["llm_error"]
        except Exception as e:  # pragma: no cover - network failures
            text, action, cited, err = "", "error", False, f"{type(e).__name__}: {e}"
        dt = (time.perf_counter() - t0) * 1000
        pts = item.get("points", [])
        hit = sum(point_covered(text, alts) for alts in pts)
        n_words = len(text.split())
        lt_ok = detect_language(text) == "lt" if text else False
        phone_ok = not LIST_MARKUP.search(text) and n_words <= 90
        summary.items.append(ItemResult(
            id=item["id"], question=item["question"], expected_action=item.get("expected_action", "answer"),
            action=action, answer=text, points_total=len(pts), points_hit=hit, cited=cited, lt_ok=lt_ok,
            phone_style_ok=phone_ok, words=n_words, latency_ms=round(dt, 1), error=err))
    return summary
