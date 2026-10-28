"""Gazetteer + structured lookup over the national shelter open-data set
(PAGD "Priedangos", data.gov.lt). Matches inflected place names in a
Lithuanian question ("Gyvenu Žirmūnuose") to an eldership (seniūnija) and
returns the nearest listed shelters for that area.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ..locales.lt.stem import STOPWORDS, stem, tokens

SOURCE_URL = "https://get.data.gov.lt/datasets/gov/pagd/priedangos/Priedanga"
SOURCE_TITLE = "PAGD priedangų sąrašas (atvirieji duomenys, data.gov.lt)"

# Words that look like place stems but are common nouns in questions.
_GENERIC = {"centr", "senamiest", "miest", "kaim", "rajon", "sav", "apskr", "nam", "gatv", "pietu", "siaur", "rytu", "vakaru"}


@dataclass
class Shelter:
    municipality: str
    eldership: str
    settlement: str
    street: str
    number: str
    name: str
    capacity: str = ""
    accessible: str = ""
    updated: str = ""

    def describe(self) -> str:
        addr = " ".join(x for x in (self.street, self.number) if x).strip()
        place = self.settlement if self.settlement and "sav." not in self.settlement else ""
        parts = [self.name or "Priedanga", addr]
        if place:
            parts.append(place)
        s = ", ".join(p for p in parts if p)
        if self.capacity:
            s += f" (talpa apie {self.capacity} žm.)"
        if self.accessible.lower() == "true":
            s += ", pritaikyta asmenims su negalia"
        return s


@dataclass
class PlaceMatch:
    eldership: str
    municipality: str
    shelters: list[Shelter] = field(default_factory=list)


class PlaceIndex:
    def __init__(self, shelters: list[Shelter]):
        self.shelters = shelters
        self.by_area: dict[tuple[str, str], list[Shelter]] = defaultdict(list)
        self.elder_stems: dict[str, set[tuple[str, str]]] = defaultdict(set)
        self.muni_stems: dict[str, set[str]] = defaultdict(set)
        for s in shelters:
            self.by_area[(s.municipality, s.eldership)].append(s)
            for t in tokens(s.eldership.replace("sen.", "")):
                if len(t) >= 4 and t not in _GENERIC:
                    self.elder_stems[t].add((s.municipality, s.eldership))
            first = s.municipality.split()[0] if s.municipality else ""
            if first:
                self.muni_stems[stem(first)].add(s.municipality)

    @classmethod
    def from_csv(cls, path: Path | str) -> "PlaceIndex":
        p = Path(path)
        if not p.exists():
            return cls([])
        with p.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        return cls([
            Shelter(municipality=r.get("savivaldybe", ""), eldership=r.get("seniunija", ""),
                    settlement=r.get("gyvenviete", ""), street=r.get("gatve", ""), number=r.get("namo_numeris", ""),
                    name=r.get("pavadinimas", ""), capacity=r.get("gyventoju_skaicius", ""),
                    accessible=r.get("pritaikyta_asmenims_su_negalia", ""), updated=r.get("atnaujinimo_data", ""))
            for r in rows
        ])

    def __len__(self) -> int:
        return len(self.shelters)

    def match(self, text: str, limit: int = 2, municipality_hint: str | None = None) -> PlaceMatch | None:
        qstems = [t for t in tokens(text) if t not in STOPWORDS]
        munis = set()
        for t in qstems:
            munis |= self.muni_stems.get(t, set())
        if municipality_hint:
            munis.add(municipality_hint)
        cands: set[tuple[str, str]] = set()
        for t in qstems:
            cands |= self.elder_stems.get(t, set())
        if munis and cands:
            narrowed = {c for c in cands if c[0] in munis}
            cands = narrowed or cands
        if not cands:
            return None
        # Prefer the area with most shelters (city elderships) when ambiguous
        muni, elder = max(cands, key=lambda c: len(self.by_area[c]))
        items = sorted(self.by_area[(muni, elder)], key=lambda s: -int(float(s.capacity or 0)))
        return PlaceMatch(eldership=elder, municipality=muni, shelters=items[:limit])
