"""Scripted demo: produce sample audio for every scenario turn.

    python -m knowledge_line.scripts.demo [--out knowledge_line/output/demo] [--text-only] [--phone]
        [--llm gemini] [--stt elevenlabs] [--tts google]

For each scenario: greeting audio, caller audio (TTS of the scripted caller
line, optionally through a simulated G.711 phone channel), STT transcript,
answer text + audio, and a transcript.md with per-stage latency.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from ..config import load_settings
from ..pipeline import Answer, KnowledgeLine, Session
from ..speech.base import to_telephony


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="knowledge_line/output/demo")
    ap.add_argument("--text-only", action="store_true", help="skip STT: feed caller text directly")
    ap.add_argument("--phone", action="store_true", help="pass caller audio through an 8 kHz G.711 channel")
    ap.add_argument("--llm"); ap.add_argument("--stt"); ap.add_argument("--tts")
    ap.add_argument("--only", nargs="*", help="scenario ids to run")
    a = ap.parse_args(argv)

    s = load_settings()
    kl = KnowledgeLine(s, llm_provider=a.llm, stt_provider=a.stt, tts_provider=a.tts)
    script = yaml.safe_load((s.profile_dir / "demo_script.yaml").read_text(encoding="utf-8"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    info = kl.describe()
    md = ["# Scripted demo run", "", f"Providers: LLM `{info['llm']}`, STT `{info['stt']}`, TTS `{info['tts']}`; "
          f"KB chunks {info['kb_chunks']}, shelters {info['shelters']}; phone channel: {a.phone}", ""]
    summary = []
    for sc in script["scenarios"]:
        if a.only and sc["id"] not in a.only:
            continue
        if sc.get("set_incident"):
            kl.incidents.set_status(sc["set_incident"]["id"], sc["set_incident"]["status"])
        d = out / sc["id"]
        d.mkdir(exist_ok=True)
        md += [f"## {sc['id']} – {sc['title']}", ""]
        session = Session()
        g = kl.greeting()
        ga = Answer(text=g, action="greeting", spoken_text=kl.speakable(g))
        gr = kl.speak(ga)
        (d / f"00_greeting.{gr.ext}").write_bytes(gr.audio)
        md += [f"**Sistema:** {g}", ""]
        for i, line in enumerate(sc["turns"], 1):
            if a.text_only:
                res = kl.turn_text(line, session)
                heard = line
            else:
                lang = sc.get("caller_language", s.locale)
                caller = kl.tts.synthesize(line, language=lang)
                caller_audio = to_telephony(caller.audio) if a.phone else caller.audio
                mime = "audio/wav" if a.phone else caller.mime
                (d / f"{i:02d}a_caller.{'wav' if a.phone else caller.ext}").write_bytes(caller_audio)
                res = kl.turn_audio(caller_audio, mime=mime, session=session)
                heard = res.transcript.text if res.transcript else line
            ans = res.answer
            if res.audio:
                (d / f"{i:02d}b_answer.{res.audio.ext}").write_bytes(res.audio.audio)
            md += [f"**Skambintojas:** {line}", ""]
            if not a.text_only:
                md += [f"*STT atpažino:* {heard}", ""]
            cites = "; ".join(f"[{c.n}] {c.title} – {c.url}" for c in ans.citations)
            md += [f"**Sistema** (`{ans.action}`): {ans.text}", ""]
            if cites:
                md += [f"Šaltiniai: {cites}", ""]
            md += [f"Delsa (ms): `{json.dumps(ans.latency_ms, ensure_ascii=False)}`", ""]
            summary.append({"scenario": sc["id"], "turn": i, "action": ans.action, "latency_ms": ans.latency_ms,
                            "heard": heard})
        if sc.get("reset_incident"):
            kl.incidents.set_status(sc["reset_incident"]["id"], sc["reset_incident"]["status"])
    (out / "transcript.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(md))
    print(f"\nAudio + transcript written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
