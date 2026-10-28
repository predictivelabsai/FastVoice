"""Small, dependency-free BM25 knowledge base over Markdown documents with
front-matter citations. Tokenisation is locale-aware (Lithuanian stemming)
so inflected questions still hit the right passage.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

from ..locales.lt.stem import tokens as lt_tokens


@dataclass
class Chunk:
    id: str
    text: str
    title: str
    url: str
    publisher: str = ""
    fetched: str = ""
    heading: str = ""


@dataclass
class Hit:
    chunk: Chunk
    score: float
    overlap: float = 0.0  # share of distinct query terms found in the chunk


@dataclass
class KnowledgeBase:
    chunks: list[Chunk] = field(default_factory=list)
    tokenizer: Callable[[str], list[str]] = lt_tokens
    k1: float = 1.4
    b: float = 0.75

    # -- loading -----------------------------------------------------------
    @classmethod
    def from_dir(cls, kb_dir: Path | str, max_chars: int = 900, tokenizer=None) -> "KnowledgeBase":
        kb = cls(tokenizer=tokenizer or lt_tokens)
        for f in sorted(Path(kb_dir).glob("*.md")):
            kb.add_markdown(f.read_text(encoding="utf-8"), doc_id=f.stem, max_chars=max_chars)
        kb.build()
        return kb

    def add_markdown(self, md: str, doc_id: str, max_chars: int = 900) -> None:
        meta, body = {}, md
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", md, flags=re.S)
        if m:
            meta = yaml.safe_load(m.group(1)) or {}
            body = m.group(2)
        title = meta.get("title", doc_id)
        heading = ""
        buf: list[str] = []
        n = 0

        def flush():
            nonlocal buf, n
            text = "\n".join(buf).strip()
            if len(text) > 40:
                self.chunks.append(Chunk(id=f"{doc_id}#{n}", text=text, title=title, url=meta.get("url", ""),
                                         publisher=meta.get("publisher", ""), fetched=str(meta.get("fetched", "")),
                                         heading=heading))
                n += 1
            buf = []

        for para in re.split(r"\n\s*\n", body):
            para = para.strip()
            if not para:
                continue
            if para.startswith("#"):
                flush()
                heading = para.lstrip("# ").strip()
                buf = [heading]
                continue
            if sum(len(x) for x in buf) + len(para) > max_chars and len(buf) > 1:
                flush()
                buf = [heading] if heading else []
            buf.append(para)
        flush()

    def build(self) -> None:
        self._docs = [self.tokenizer(f"{c.title} {c.heading} {c.text}") for c in self.chunks]
        self._tf = [Counter(d) for d in self._docs]
        self._len = [len(d) for d in self._docs]
        self._avg = (sum(self._len) / len(self._len)) if self._len else 0.0
        df: Counter = Counter()
        for d in self._docs:
            df.update(set(d))
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    # -- search ------------------------------------------------------------
    def search(self, query: str, k: int = 4) -> list[Hit]:
        if not self.chunks:
            return []
        q = self.tokenizer(query)
        qset = set(q)
        scores = []
        for i, tf in enumerate(self._tf):
            s = 0.0
            for t in q:
                if t not in tf:
                    continue
                f = tf[t]
                s += self._idf.get(t, 0.0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self._len[i] / (self._avg or 1)))
            if s > 0:
                scores.append((s, i))
        scores.sort(reverse=True)
        return [Hit(self.chunks[i], s, len(qset & set(self._tf[i])) / max(1, len(qset))) for s, i in scores[:k]]
