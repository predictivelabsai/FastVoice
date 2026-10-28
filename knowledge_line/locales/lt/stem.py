"""Very light Lithuanian stemmer / tokenizer for retrieval and place matching.

Lithuanian is highly inflected ("Žirmūnuose", "Žirmūnų", "Žirmūnai" are the
same place). Stripping the most frequent case endings gives a large recall
gain for BM25 and gazetteer matching without external dependencies.
"""

from __future__ import annotations

import re
import unicodedata

# Longest first. Covers noun/adjective case endings and common verb endings.
SUFFIXES = sorted(
    {
        "iuose", "uose", "iuje", "iaus", "aus", "iose", "ose", "yse", "ėse", "ese", "iame", "ame", "oje", "ėje", "yje", "uje",
        "iams", "ams", "oms", "ėms", "ims", "ums", "iems", "ųjų", "iųjų", "ajam", "ajai", "ajame",
        "iais", "ais", "omis", "ėmis", "imis", "umis", "iomis", "iumi", "umi", "imi",
        "ių", "ų", "iai", "ai", "ios", "os", "ės", "ys", "us", "ius", "is", "as", "ias", "es",
        "ui", "iui", "ei", "ai", "ą", "ę", "į", "ų", "ių", "ia", "a", "ė", "e", "y", "i", "o", "u",
        "ti", "tis", "kite", "ite", "ate", "ote", "ėte", "si", "osi", "asi", "isi",
    },
    key=len,
    reverse=True,
)

STOPWORDS = set(
    """ir ar bet o kad jei jeigu kai kur kas ką kaip kuo kuri kuris kurie kurios tai tas ta
    tie tos šis ši jis ji jie jos jo jų man mane mano mus mūsų jums jūsų jus aš tu mes jūs
    yra buvo bus būti gali galima reikia turi turite labai taip pat ne nė dar jau tik
    į iš su be per prie nuo iki po už apie dėl ant tarp pas pagal virš prieš
    sveiki laba diena prašau ačiū""".split()
)


def fold(s: str) -> str:
    """Lower-case and strip diacritics (ą->a, ž->z) for accent-insensitive matching."""
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def stem(word: str) -> str:
    w = word.lower()
    if len(w) <= 3:
        return fold(w)
    for suf in SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            break
    return fold(w)


def tokens(text: str, drop_stopwords: bool = True) -> list[str]:
    words = re.findall(r"[0-9A-Za-zĄČĘĖĮŠŲŪŽąčęėįšųūž]+", text)
    out = []
    for w in words:
        lw = w.lower()
        if drop_stopwords and lw in STOPWORDS:
            continue
        out.append(stem(lw))
    return out
