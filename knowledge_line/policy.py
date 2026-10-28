"""Deterministic call-handling rules that must never depend on the LLM:
emergency escalation to 112, requests for a human, unsupported language,
"slower / repeat" and "I did not understand" turns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LT_LETTERS = set("ąčęėįšųūž")
PL_LETTERS = set("łśćźżńó")
UK_LETTERS = set("іїєґ")
EN_WORDS = {"the", "is", "are", "where", "what", "how", "hello", "help", "i", "my", "you", "shelter", "please", "can"}
LT_WORDS = {"ir", "kur", "kas", "kaip", "ką", "ar", "man", "yra", "laba", "diena", "sveiki", "prašau", "ačiū", "jei", "mano", "daryti"}


def detect_language(text: str) -> str:
    t = text.lower()
    letters = [c for c in t if c.isalpha()]
    if not letters:
        return "lt"
    cyr = sum("а" <= c <= "я" or c in "ёіїєґ" for c in letters)
    if cyr / len(letters) > 0.3:
        return "uk" if any(c in UK_LETTERS for c in t) else "ru"
    if any(c in PL_LETTERS for c in t) and not any(c in "ėįšųūž" for c in t):
        return "pl"
    if any(c in LT_LETTERS for c in t):
        return "lt"
    words = set(re.findall(r"[a-z']+", t))
    if len(words & EN_WORDS) >= 2 and not words & LT_WORDS:
        return "en"
    return "lt"


@dataclass
class Intent:
    kind: str  # emergency | human | language | slower | simpler | question
    language: str = "lt"


class Policy:
    def __init__(self, cfg: dict):
        def comp(key):
            pats = cfg.get(key, []) or []
            return [re.compile(p, re.I) for p in pats]

        self.emergency = comp("emergency_patterns")
        self.human = comp("human_patterns")
        self.slower = comp("slower_patterns")
        self.simpler = comp("simpler_patterns")
        self.shelter = comp("shelter_intent_patterns")

    @staticmethod
    def _any(pats, text: str) -> bool:
        return any(p.search(text) for p in pats)

    def classify(self, text: str, has_previous_answer: bool = False) -> Intent:
        t = " " + text.strip() + " "
        lang = detect_language(text)
        if lang != "lt":
            return Intent("language", lang)
        if self._any(self.emergency, t):
            return Intent("emergency")
        if self._any(self.human, t):
            return Intent("human")
        short = len(text.split()) <= 6
        if has_previous_answer and short and self._any(self.slower, t):
            return Intent("slower")
        if has_previous_answer and short and self._any(self.simpler, t):
            return Intent("simpler")
        return Intent("question")

    def is_shelter_question(self, text: str) -> bool:
        return self._any(self.shelter, text)
