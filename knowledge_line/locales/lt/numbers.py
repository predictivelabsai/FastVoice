"""Lithuanian number, ordinal and date verbalisation for TTS.

Covers the cases that matter on a phone line: cardinals with masculine /
feminine agreement, digit-by-digit service numbers (112, 1852), ordinal
days, years and months. Grammatical case agreement beyond nominative is out
of scope; callers can steer gender with :func:`cardinal` ``feminine=True``.
"""

from __future__ import annotations

ONES_M = ["nulis", "vienas", "du", "trys", "keturi", "penki", "šeši", "septyni", "aštuoni", "devyni"]
ONES_F = ["nulis", "viena", "dvi", "trys", "keturios", "penkios", "šešios", "septynios", "aštuonios", "devynios"]
TEENS = [
    "dešimt", "vienuolika", "dvylika", "trylika", "keturiolika", "penkiolika",
    "šešiolika", "septyniolika", "aštuoniolika", "devyniolika",
]
TENS = ["", "dešimt", "dvidešimt", "trisdešimt", "keturiasdešimt", "penkiasdešimt",
        "šešiasdešimt", "septyniasdešimt", "aštuoniasdešimt", "devyniasdešimt"]

# Ordinals, masculine plural nominative (used for years: "dvidešimt šeštieji metai")
ORD_M_PL = ["", "pirmieji", "antrieji", "tretieji", "ketvirtieji", "penktieji", "šeštieji",
            "septintieji", "aštuntieji", "devintieji"]
ORD_M_PL_TEENS = ["dešimtieji", "vienuoliktieji", "dvyliktieji", "tryliktieji", "keturioliktieji",
                  "penkioliktieji", "šešioliktieji", "septynioliktieji", "aštuonioliktieji",
                  "devynioliktieji"]
ORD_M_PL_TENS = ["", "dešimtieji", "dvidešimtieji", "trisdešimtieji", "keturiasdešimtieji",
                 "penkiasdešimtieji", "šešiasdešimtieji", "septyniasdešimtieji",
                 "aštuoniasdešimtieji", "devyniasdešimtieji"]
# Ordinals, feminine singular nominative definite (used for days: "dvidešimtoji")
ORD_F = ["", "pirmoji", "antroji", "trečioji", "ketvirtoji", "penktoji", "šeštoji", "septintoji",
         "aštuntoji", "devintoji"]
ORD_F_TEENS = ["dešimtoji", "vienuoliktoji", "dvyliktoji", "tryliktoji", "keturioliktoji",
               "penkioliktoji", "šešioliktoji", "septynioliktoji", "aštuonioliktoji",
               "devynioliktoji"]
ORD_F_TENS = ["", "dešimtoji", "dvidešimtoji", "trisdešimtoji"]

MONTHS_GEN = ["sausio", "vasario", "kovo", "balandžio", "gegužės", "birželio", "liepos",
              "rugpjūčio", "rugsėjo", "spalio", "lapkričio", "gruodžio"]

DIGITS = ONES_M

# Dative forms (for "pasiruoškite 72 valandoms" -> "septyniasdešimt dviem valandoms")
ONES_DAT_M = ["nuliui", "vienam", "dviem", "trims", "keturiems", "penkiems", "šešiems", "septyniems",
              "aštuoniems", "devyniems"]
ONES_DAT_F = ["nuliui", "vienai", "dviem", "trims", "keturioms", "penkioms", "šešioms", "septynioms",
              "aštuonioms", "devynioms"]
TEENS_DAT = ["dešimčiai", "vienuolikai", "dvylikai", "trylikai", "keturiolikai", "penkiolikai",
             "šešiolikai", "septyniolikai", "aštuoniolikai", "devyniolikai"]
TENS_DAT = ["", "dešimčiai", "dvidešimčiai", "trisdešimčiai", "keturiasdešimčiai", "penkiasdešimčiai",
            "šešiasdešimčiai", "septyniasdešimčiai", "aštuoniasdešimčiai", "devyniasdešimčiai"]
# Feminine ordinal accusative for clock hours ("keturioliktą valandą")
ORD_F_ACC = ["", "pirmą", "antrą", "trečią", "ketvirtą", "penktą", "šeštą", "septintą", "aštuntą",
             "devintą", "dešimtą", "vienuoliktą", "dvyliktą", "tryliktą", "keturioliktą",
             "penkioliktą", "šešioliktą", "septynioliktą", "aštuonioliktą", "devynioliktą",
             "dvidešimtą", "dvidešimt pirmą", "dvidešimt antrą", "dvidešimt trečią",
             "dvidešimt ketvirtą"]


def cardinal_dative(n: int, feminine: bool = False) -> str:
    """Dative cardinal; only the final component is declined (colloquial standard)."""
    if n < 0 or n >= 1000:
        return cardinal(n, feminine)
    head, last = divmod(n, 100)
    prefix = (cardinal(head * 100) + " ") if head else ""
    if last == 0:
        return cardinal(n, feminine)
    if 10 <= last < 20:
        return prefix + TEENS_DAT[last - 10]
    t, o = divmod(last, 10)
    if o == 0:
        return prefix + TENS_DAT[t]
    return prefix + (TENS[t] + " " if t else "") + (ONES_DAT_F if feminine else ONES_DAT_M)[o]


def clock_hour(h: int) -> str:
    """'14' -> 'keturioliktą' (as in 'keturioliktą valandą')."""
    return ORD_F_ACC[h] if 0 < h < len(ORD_F_ACC) else cardinal(h)


def _scale_word(n: int, forms: tuple[str, str, str]) -> str:
    """Pick the Lithuanian counted-noun form: (1, 2-9, 0/10-20) e.g. tūkstantis/tūkstančiai/tūkstančių."""
    if n % 10 == 0 or 10 <= n % 100 <= 20:
        return forms[2]
    if n % 10 == 1:
        return forms[0]
    return forms[1]


def _below_thousand(n: int, feminine: bool = False) -> list[str]:
    words: list[str] = []
    hundreds, rest = divmod(n, 100)
    if hundreds:
        words.append("šimtas" if hundreds == 1 else f"{ONES_M[hundreds]} šimtai")
    if 10 <= rest < 20:
        words.append(TEENS[rest - 10])
    else:
        tens, ones = divmod(rest, 10)
        if tens:
            words.append(TENS[tens])
        if ones:
            words.append((ONES_F if feminine else ONES_M)[ones])
    return words


def cardinal(n: int, feminine: bool = False) -> str:
    """Verbalise a non-negative integer (up to 999 999 999)."""
    if n < 0:
        return "minus " + cardinal(-n, feminine)
    if n == 0:
        return "nulis"
    words: list[str] = []
    millions, rest = divmod(n, 1_000_000)
    thousands, rest = divmod(rest, 1000)
    if millions:
        if millions != 1:
            words += _below_thousand(millions)
        words.append(_scale_word(millions, ("milijonas", "milijonai", "milijonų")))
    if thousands:
        if thousands != 1:
            words += _below_thousand(thousands)
        words.append(_scale_word(thousands, ("tūkstantis", "tūkstančiai", "tūkstančių")))
    if rest:
        words += _below_thousand(rest, feminine)
    return " ".join(words)


def digits(s: str) -> str:
    """Read a digit string one digit at a time: '112' -> 'vienas, vienas, du'."""
    return ", ".join(DIGITS[int(c)] for c in s if c.isdigit())


def _ordinal(n: int, units, teens, tens_words) -> str:
    """Compound ordinal: only the last component is ordinal ("dvidešimt pirmoji")."""
    if n <= 0:
        raise ValueError("ordinal needs n >= 1")
    head, last = divmod(n, 100)
    prefix = cardinal(head * 100) + " " if head else ""
    if 10 <= last < 20:
        return prefix + teens[last - 10]
    t, o = divmod(last, 10)
    if o == 0:
        if t == 0:  # round hundreds/thousands: fall back to cardinal + ordinal-ish suffix
            return cardinal(n)
        return prefix + tens_words[t]
    return prefix + (TENS[t] + " " if t else "") + units[o]


def ordinal_day(n: int) -> str:
    """Day of month, feminine definite nominative: 20 -> 'dvidešimtoji'."""
    if not 1 <= n <= 31:
        raise ValueError(n)
    return _ordinal(n, ORD_F, ORD_F_TEENS, ORD_F_TENS)


def ordinal_year(n: int) -> str:
    """Year, masculine plural ordinal: 2026 -> 'du tūkstančiai dvidešimt šeštieji'."""
    thousands, rest = divmod(n, 1000)
    if rest == 0:
        return {1: "tūkstantieji", 2: "dutūkstantieji"}.get(thousands, cardinal(n))
    prefix = cardinal(thousands * 1000) + " " if thousands else ""
    return prefix + _ordinal(rest, ORD_M_PL, ORD_M_PL_TEENS, ORD_M_PL_TENS)


def date_phrase(year: int | None, month: int, day: int) -> str:
    """'2026-11-20' -> 'du tūkstančiai dvidešimt šeštųjų metų lapkričio dvidešimtoji'.

    Years are given in genitive plural ("...šeštųjų metų") as is natural before a month.
    """
    parts = []
    if year:
        y = ordinal_year(year)
        # nominative plural -ieji -> genitive plural -ųjų for the last word
        words = y.split(" ")
        if words[-1].endswith("ieji"):
            words[-1] = words[-1][:-4] + "ųjų"
        parts.append(" ".join(words) + " metų")
    parts.append(MONTHS_GEN[month - 1])
    parts.append(ordinal_day(day))
    return " ".join(parts)


ONES_ACC_M = ["nulį", "vieną", "du", "tris", "keturis", "penkis", "šešis", "septynis", "aštuonis", "devynis"]
ONES_ACC_F = ["nulį", "vieną", "dvi", "tris", "keturias", "penkias", "šešias", "septynias", "aštuonias",
              "devynias"]


def cardinal_accusative(n: int, feminine: bool = False) -> str:
    """Accusative cardinal ("aštuonis metrus", "septyniasdešimt dvi valandas")."""
    if n < 0 or n >= 1000:
        return cardinal(n, feminine)
    head, last = divmod(n, 100)
    prefix = (cardinal(head * 100) + " ") if head else ""
    if last == 0 or 10 <= last < 20:
        return cardinal(n, feminine)
    t, o = divmod(last, 10)
    if o == 0:
        return cardinal(n, feminine)
    return prefix + (TENS[t] + " " if t else "") + (ONES_ACC_F if feminine else ONES_ACC_M)[o]
