"""Compare providers on Lithuanian quality and latency.

    python -m knowledge_line.scripts.compare_providers [--llm gemini mistral mock]
        [--tts google elevenlabs] [--stt google elevenlabs] [--phone] [--out knowledge_line/results]

1. LLM: runs the profile's LT eval set (action accuracy, answer-point
   coverage, citation rate, Lithuanian-only and phone-style checks, latency).
2. Speech: synthesises LT reference sentences with each TTS, optionally
   passes them through a simulated G.711 phone channel (--phone), and
   transcribes them with each STT -> WER / CER per TTS x STT pair, plus
   TTS and STT latency. This is a cheap proxy for LT intelligibility; it is
   not a substitute for a human MOS test.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

from ..config import load_settings
from ..evaluation import cer, load_items, run_eval, wer
from ..llm import available_llm_providers
from ..pipeline import KnowledgeLine
from ..speech import available_stt, make_stt, make_tts
from ..speech.base import to_telephony

SPEECH_SENTENCES = [
    "Oro pavojaus atveju vykite į artimiausią priedangą arba slėpkitės rūsyje.",
    "Jei kyla pavojus gyvybei ar sveikatai, nedelsdami skambinkite 112.",
    "Apie elektros tiekimo sutrikimus praneškite ESO telefonu 1852.",
    "Išvykimo krepšyje turėkite dokumentus, vaistų ir vandens 72 valandoms.",
    "Esant cheminei taršai uždarykite langus ir duris, išjunkite vėdinimą.",
    "Priedangos pažymėtos geltonu kvadratu su užrašu PRIEDANGA.",
    "Konsultavimo linija 1856 veikia visą parą, septynias dienas per savaitę.",
    "Žirmūnų seniūnijoje artimiausia priedanga yra požeminėje automobilių stovėjimo aikštelėje.",
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm", nargs="*", default=None)
    ap.add_argument("--tts", nargs="*", default=None)
    ap.add_argument("--stt", nargs="*", default=None)
    ap.add_argument("--phone", action="store_true", help="simulate 8 kHz G.711 telephone channel")
    ap.add_argument("--skip-llm", action="store_true")
    ap.add_argument("--skip-speech", action="store_true")
    ap.add_argument("--out", default="knowledge_line/results")
    a = ap.parse_args(argv)

    s = load_settings()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    report: dict = {"generated": stamp, "locale": s.locale, "llm": [], "speech": []}
    md = [f"# Lithuanian provider comparison ({stamp})", ""]

    if not a.skip_llm:
        llms = a.llm or [p for p in ("gemini", "mistral", "mock") if p in available_llm_providers()]
        items = load_items(s.profile_dir / s.profile.get("eval_file", "eval/lt_eval.yaml"))
        md += ["## LLM (RAG answers on the LT eval set)", "",
               "| provider | action acc. | answer-point coverage | citations | LT-only | phone style | avg words | p50 ms | p95 ms | errors |",
               "|---|---|---|---|---|---|---|---|---|---|"]
        for p in llms:
            kl = KnowledgeLine(s, llm_provider=p, stt_provider="mock", tts_provider="mock")
            summ = run_eval(kl, items)
            m = summ.metrics()
            report["llm"].append({"metrics": m, "items": [i.__dict__ for i in summ.items]})
            md.append(f"| {m['provider']} | {m['action_accuracy']} | {m['answer_point_coverage']} | {m['citation_rate']} | "
                      f"{m['lithuanian_rate']} | {m['phone_style_rate']} | {m['avg_words']} | {m['latency_p50_ms']} | "
                      f"{m['latency_p95_ms']} | {m['errors']} |")
            print(json.dumps(m, ensure_ascii=False))
        md.append("")
        for r in report["llm"]:
            md += [f"### {r['metrics']['provider']} – answers", ""]
            for it in r["items"]:
                md.append(f"- **{it['id']}** ({it['action']}, {it['points_hit']}/{it['points_total']}): {it['answer'][:400]}")
            md.append("")

    if not a.skip_speech:
        avail = available_stt(s)
        tts_list = a.tts or [p for p in ("google", "elevenlabs") if p in avail] or ["mock"]
        stt_list = a.stt or [p for p in ("google", "elevenlabs") if p in avail] or ["mock"]
        kl = KnowledgeLine(s, llm_provider="mock", stt_provider="mock", tts_provider="mock")
        md += [f"## Speech round-trip (TTS → {'G.711 phone channel → ' if a.phone else ''}STT), {len(SPEECH_SENTENCES)} LT sentences", "",
               "| TTS | STT | WER | CER | TTS ms (mean) | STT ms (mean) | errors |", "|---|---|---|---|---|---|---|"]
        for tname in tts_list:
            try:
                tts = make_tts(s, tname)
            except Exception as e:
                md.append(f"| {tname} | – | – | – | – | – | {type(e).__name__} |")
                continue
            clips, tts_ms, errs = [], [], 0
            for sent in SPEECH_SENTENCES:
                try:
                    r = tts.synthesize(kl.speakable(sent), language=s.locale)
                    audio = to_telephony(r.audio) if a.phone else r.audio
                    clips.append((sent, audio, "audio/wav" if a.phone else r.mime))
                    tts_ms.append(r.latency_ms)
                except Exception as e:
                    errs += 1
                    print("TTS error", tname, type(e).__name__, str(e)[:200])
            for sname in stt_list:
                try:
                    stt = make_stt(s, sname)
                except Exception as e:
                    md.append(f"| {tname} | {sname} | – | – | – | – | {type(e).__name__} |")
                    continue
                w, c, stt_ms, serr, samples = [], [], [], 0, []
                for sent, audio, mime in clips:
                    try:
                        tr = stt.transcribe(audio, mime=mime, language=s.locale)
                        ref = kl.speakable(sent)  # compare in spoken form (numbers as words)
                        hyp = kl.speakable(tr.text)
                        w.append(wer(ref, hyp)); c.append(cer(ref, hyp)); stt_ms.append(tr.latency_ms)
                        samples.append({"ref": sent, "hyp": tr.text})
                    except Exception as e:
                        serr += 1
                        print("STT error", sname, type(e).__name__, str(e)[:200])
                row = {"tts": f"{tname}:{getattr(tts, 'voice', '') or getattr(tts, 'voice_id', '')}", "stt": sname,
                       "wer": round(statistics.mean(w), 3) if w else None, "cer": round(statistics.mean(c), 3) if c else None,
                       "tts_ms": round(statistics.mean(tts_ms)) if tts_ms else None,
                       "stt_ms": round(statistics.mean(stt_ms)) if stt_ms else None, "errors": errs + serr,
                       "phone_channel": a.phone, "samples": samples}
                report["speech"].append(row)
                print(json.dumps({k: v for k, v in row.items() if k != "samples"}, ensure_ascii=False))
                md.append(f"| {row['tts']} | {sname} | {row['wer']} | {row['cer']} | {row['tts_ms']} | {row['stt_ms']} | {row['errors']} |")
        md.append("")

    (out / f"compare-{stamp}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (out / f"compare-{stamp}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\nWrote {out / f'compare-{stamp}.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
