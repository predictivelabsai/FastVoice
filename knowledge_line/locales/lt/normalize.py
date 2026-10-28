"""Lithuanian text normalisation for TTS (numbers, dates, times, units,
abbreviations, service phone numbers, URLs) plus pronunciation lexicon.

The goal is that *any* TTS engine receives plain spoken Lithuanian, so that
"Skambinkite 112, 2026-11-20 14:00" is read as a Lithuanian speaker would
say it, rather than relying on each vendor's own (often weak) LT front-end.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .numbers import MONTHS_GEN, cardinal, cardinal_accusative, cardinal_dative, clock_hour, date_phrase, digits

LEXICON_PATH = Path(__file__).with_name("lexicon.yaml")

# Nouns that take feminine numerals (stems, lower-case). Enough for the
# civil-protection domain; extend in lexicon.yaml -> feminine_stems.
DEFAULT_FEMININE_STEMS = (
    "valand", "par", "dien", "minut", "sekund", "savait", "priedang", "sien", "eil",
    "kart", "vietos", "viet", "tonos", "ton", "taisykl", "grup",
)

ABBREVIATIONS = {
    r"\bpvz\.": "pavyzdžiui",
    r"\bt\.\s?y\.": "tai yra",
    r"\bir kt\.": "ir kiti",
    r"\bir pan\.": "ir panašiai",
    r"\btel\.": "telefonas",
    r"\bnr\.": "numeris",
    r"\bNr\.": "numeris",
    r"\bg\.(?=\s|$)": "gatvė",
    r"\bsav\.": "savivaldybė",
    r"\bapskr\.": "apskritis",
    r"\bm\. sav\.": "miesto savivaldybė",
    r"\br\. sav\.": "rajono savivaldybė",
    r"\bval\.": "valandą",
    r"\bmin\.": "minučių",
    r"\bproc\.": "procentų",
    r"\bžr\.": "žiūrėkite",
}

UNITS = {
    "l": ("litras", "litrai", "litrų"),
    "km": ("kilometras", "kilometrai", "kilometrų"),
    "m": ("metras", "metrai", "metrų"),
    "kg": ("kilogramas", "kilogramai", "kilogramų"),
    "kW": ("kilovatas", "kilovatai", "kilovatų"),
    "%": ("procentas", "procentai", "procentų"),
    "°C": ("laipsnis Celsijaus", "laipsniai Celsijaus", "laipsnių Celsijaus"),
    "Eur": ("euras", "eurai", "eurų"),
    "€": ("euras", "eurai", "eurų"),
}

PHONE_CONTEXT = re.compile(r"(tel|telefon|numer|skambin|skambut|surink|112)", re.I)


def unit_form(n: int, forms: tuple[str, str, str]) -> str:
    if n % 10 == 0 or 10 <= n % 100 <= 20:
        return forms[2]
    if n % 10 == 1:
        return forms[0]
    return forms[1]


@dataclass
class Lexicon:
    aliases: dict[str, str] = field(default_factory=dict)  # written -> spoken
    feminine_stems: tuple[str, ...] = DEFAULT_FEMININE_STEMS
    service_numbers: tuple[str, ...] = ("112",)

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Lexicon":
        p = Path(path) if path else LEXICON_PATH
        data = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
        aliases = {}
        for entry in data.get("terms", []):
            aliases[entry["written"]] = entry["spoken"]
        fem = tuple(data.get("feminine_stems", [])) or DEFAULT_FEMININE_STEMS
        svc = tuple(str(x) for x in data.get("service_numbers", ["112"]))
        return cls(aliases=aliases, feminine_stems=fem, service_numbers=svc)


def _is_dative_plural(next_word: str) -> bool:
    w = next_word.lower().strip(",.;:!?()\"'„“")
    return len(w) > 4 and w.endswith(("oms", "ams", "ims", "ėms", "ums", "iems"))


def _num(n: int, next_word: str | None, stems: tuple[str, ...]) -> str:
    fem = bool(next_word) and _is_feminine(next_word, stems)
    if next_word and _is_dative_plural(next_word):
        return cardinal_dative(n, fem)
    w = next_word.lower().strip(",.;:!?()\"'„“") if next_word else ""
    if (w.endswith("us") and len(w) > 3) or (fem and w.endswith("as")) or w.endswith(("ą", "į")):
        return cardinal_accusative(n, fem)
    return cardinal(n, fem)


def _is_feminine(next_word: str, stems: tuple[str, ...]) -> bool:
    w = next_word.lower().strip(",.;:!?()\"'„“")
    return any(w.startswith(s) for s in stems)


class LithuanianNormalizer:
    """Turn written Lithuanian into speakable Lithuanian."""

    def __init__(self, lexicon: Lexicon | None = None):
        self.lexicon = lexicon or Lexicon.load()

    # -- public -----------------------------------------------------------
    def __call__(self, text: str) -> str:
        return self.normalize(text)

    def normalize(self, text: str) -> str:
        t = self._strip_markup(text)
        t = self._urls(t)
        t = self._aliases(t)
        t = self._dates(t)
        t = self._times(t)
        t = self._phones(t)
        t = self._abbreviations(t)
        t = self._units(t)
        t = self._ranges(t)
        t = self._decimals(t)
        t = self._integers(t)
        t = re.sub(r"[ \t]+", " ", t)
        return t.strip()

    # -- steps --------------------------------------------------------------
    @staticmethod
    def _strip_markup(t: str) -> str:
        t = re.sub(r"\[(\d+)\]", "", t)  # citation markers [1]
        t = re.sub(r"[*_#`>]+", "", t)
        t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
        return t

    def _urls(self, t: str) -> str:
        t = re.sub(r"https?://(www\.)?", "", t)

        def dom(m: re.Match) -> str:
            d = m.group(0).rstrip("/")
            if d in self.lexicon.aliases:
                return self.lexicon.aliases[d]
            return d.replace(".", " taškas ").replace("/", " ")

        return re.sub(r"\b[\w-]+\.(lt|lrv\.lt|eu|com|org)\b(/[\w\-/]*)?", dom, t)

    def _aliases(self, t: str) -> str:
        for written in sorted(self.lexicon.aliases, key=len, reverse=True):
            spoken = self.lexicon.aliases[written]
            t = re.sub(rf"(?<![\w]){re.escape(written)}(?![\w])", spoken, t)
        return t

    @staticmethod
    def _dates(t: str) -> str:
        def iso(m: re.Match) -> str:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= mo <= 12 and 1 <= d <= 31:
                return date_phrase(y, mo, d)
            return m.group(0)

        t = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", iso, t)
        months = "|".join(MONTHS_GEN)

        def written(m: re.Match) -> str:
            y = int(m.group(1)) if m.group(1) else None
            mo = MONTHS_GEN.index(m.group(2).lower()) + 1
            return date_phrase(y, mo, int(m.group(3)))

        t = re.sub(rf"\b(?:(\d{{4}})\s*m\.\s*)?({months})\s+(\d{{1,2}})\s*d\.", written, t, flags=re.I)
        return t

    @staticmethod
    def _times(t: str) -> str:
        def hm(m: re.Match) -> str:
            h, mi = int(m.group(1)), int(m.group(2))
            if h > 24 or mi > 59:
                return m.group(0)
            if mi == 0:
                return f"{clock_hour(h)} valandą"
            hours = unit_form(h, ("valanda", "valandos", "valandų"))
            mins = unit_form(mi, ("minutė", "minutės", "minučių"))
            return f"{cardinal(h, True)} {hours} {cardinal(mi, True)} {mins}"

        return re.sub(r"\b(\d{1,2}):(\d{2})\b(?:\s*val\.)?", hm, t)

    def _phones(self, t: str) -> str:
        # International / long numbers: +370 5 123 4567 -> digit groups
        def intl(m: re.Match) -> str:
            groups = re.findall(r"\d+", m.group(0))
            return "plius " + "; ".join(digits(g) for g in groups) if m.group(0).startswith("+") else "; ".join(digits(g) for g in groups)

        t = re.sub(r"\+\d{3}(?:[ \-]?\d{1,4}){2,4}", intl, t)
        # Always-digitwise service numbers (112)
        for svc in self.lexicon.service_numbers:
            t = re.sub(rf"(?<![\d,.]){svc}(?![\d,.]\d)", digits(svc), t)

        # 3-5 digit short numbers in phone context (1852, 1856...)
        def short(m: re.Match) -> str:
            start = max(0, m.start() - 40)
            ctx = t[start:m.start()]
            if PHONE_CONTEXT.search(ctx):
                return digits(m.group(0))
            return m.group(0)

        return re.sub(r"(?<![\d,.])1\d{2,4}(?![\d,.]\d)", short, t)

    @staticmethod
    def _abbreviations(t: str) -> str:
        for pat, rep in ABBREVIATIONS.items():
            t = re.sub(pat, rep, t)
        return t

    @staticmethod
    def _units(t: str) -> str:
        keys = sorted(UNITS, key=len, reverse=True)
        alt = "|".join(re.escape(k) for k in keys)

        def rep(m: re.Match) -> str:
            raw, unit = m.group(1), m.group(2)
            if "," in raw:
                a, b = raw.split(",")
                return f"{cardinal(int(a))} kablelis {cardinal(int(b))} {UNITS[unit][2]}"
            n = int(raw)
            return f"{cardinal(n)} {unit_form(n, UNITS[unit])}"

        return re.sub(rf"(?<![\w,])(\d+(?:,\d+)?)\s?({alt})(?=[\s.,;:!?)]|$)", rep, t)

    def _ranges(self, t: str) -> str:
        def rep(m: re.Match) -> str:
            a, b = int(m.group(1)), int(m.group(2))
            nxt = t[m.end():].split(maxsplit=1)
            w = nxt[0] if nxt else None
            return f"{_num(a, w, self.lexicon.feminine_stems)} ar {_num(b, w, self.lexicon.feminine_stems)}"

        return re.sub(r"\b(\d+)\s?[–-]\s?(\d+)\b", rep, t)

    @staticmethod
    def _decimals(t: str) -> str:
        return re.sub(
            r"\b(\d+),(\d+)\b",
            lambda m: f"{cardinal(int(m.group(1)))} kablelis {cardinal(int(m.group(2)))}",
            t,
        )

    def _integers(self, t: str) -> str:
        out: list[str] = []
        pos = 0
        for m in re.finditer(r"\b(\d+)([A-ZĄČĘĖĮŠŲŪŽ])?\b", t):
            out.append(t[pos:m.start()])
            nxt = t[m.end():].split(maxsplit=1)
            word = cardinal(int(m.group(1))) if m.group(2) else _num(int(m.group(1)), nxt[0] if nxt else None, self.lexicon.feminine_stems)
            out.append(word + (f" {m.group(2)}" if m.group(2) else ""))
            pos = m.end()
        out.append(t[pos:])
        return "".join(out)


def normalize(text: str) -> str:
    return LithuanianNormalizer().normalize(text)
