"""Command-line interface.

    python -m knowledge_line.cli info
    python -m knowledge_line.cli ask "Kur slėptis per oro pavojų?" [--say out.mp3]
    python -m knowledge_line.cli listen question.wav [--say answer.mp3]
    python -m knowledge_line.cli chat                    # interactive text session
    python -m knowledge_line.cli normalize "Skambinkite 112, 2026-11-20 14:00"
    python -m knowledge_line.cli greeting [--say greeting.mp3]

Providers: --llm gemini|mistral|mock --stt google|elevenlabs|mock --tts google|elevenlabs|mock
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from pathlib import Path


def _kl(a):
    from .config import load_settings
    from .pipeline import KnowledgeLine

    return KnowledgeLine(load_settings(a.config), llm_provider=a.llm, stt_provider=a.stt, tts_provider=a.tts,
                         llm_model=a.model)


def _print_answer(res, as_json: bool):
    if as_json:
        print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
        return
    a = res.answer
    if res.transcript:
        print(f"🎙  STT ({res.transcript.provider}): {res.transcript.text}")
    print(f"💬 [{a.action}] {a.text}")
    for c in a.citations:
        print(f"   [{c.n}] {c.title} – {c.url}")
    if a.place:
        print(f"   📍 {a.place['eldership']} ({a.place['municipality']})")
    print(f"   ⏱  {a.latency_ms}  llm={a.llm}")


def _save(res, path: str | None):
    if path and res.audio:
        p = Path(path)
        if p.suffix.lstrip(".") != res.audio.ext:
            p = p.with_suffix("." + res.audio.ext)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(res.audio.audio)
        print(f"   🔊 {p} ({res.audio.provider}/{res.audio.voice})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="knowledge_line", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="extra YAML merged over configs/default.yaml")
    ap.add_argument("--llm")
    ap.add_argument("--model")
    ap.add_argument("--stt")
    ap.add_argument("--tts")
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info")
    p = sub.add_parser("ask"); p.add_argument("question"); p.add_argument("--say")
    p = sub.add_parser("listen"); p.add_argument("audio"); p.add_argument("--say")
    sub.add_parser("chat")
    p = sub.add_parser("normalize"); p.add_argument("text")
    p = sub.add_parser("greeting"); p.add_argument("--say")
    a = ap.parse_args(argv)

    if a.cmd == "normalize":
        from .locales.lt.normalize import normalize

        print(normalize(a.text))
        return 0
    kl = _kl(a)
    if a.cmd == "info":
        print(json.dumps(kl.describe(), ensure_ascii=False, indent=2))
    elif a.cmd == "greeting":
        from .pipeline import Answer, TurnResult

        text = kl.greeting()
        ans = Answer(text=text, action="greeting", spoken_text=kl.speakable(text))
        print(text)
        if a.say:
            _save(TurnResult(answer=ans, audio=kl.speak(ans)), a.say)
    elif a.cmd == "ask":
        res = kl.turn_text(a.question, with_audio=bool(a.say))
        _print_answer(res, a.json)
        _save(res, a.say)
    elif a.cmd == "listen":
        data = Path(a.audio).read_bytes()
        mime = mimetypes.guess_type(a.audio)[0] or "audio/wav"
        res = kl.turn_audio(data, mime=mime, with_audio=bool(a.say))
        _print_answer(res, a.json)
        _save(res, a.say)
    elif a.cmd == "chat":
        from .pipeline import Session

        s = Session()
        print(kl.greeting())
        while True:
            try:
                q = input("> ").strip()
            except EOFError:
                break
            if q in ("", "exit", "quit"):
                break
            _print_answer(kl.turn_text(q, s, with_audio=False), a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
