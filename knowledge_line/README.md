# FastVoice Knowledge Line (`knowledge_line/`)

A provider-configurable **speech → retrieval-grounded LLM → speech** question-answering
line, built as a self-contained module of FastVoice. **Lithuanian (`lt-LT`) is the
first-class locale**; the shipped profile is a public civil-protection information line
grounded in official Lithuanian guidance (LT72.lt / PAGD, Bendrasis pagalbos centras, ESO)
and the national shelter open-data set.

It runs fully offline with mock providers (no keys) and switches to real providers by
configuration.

```
caller audio ─► STT (ElevenLabs Scribe | Google Cloud STT | Gemini | Azure* | Tilde* | mock)
             ─► policy (112 escalation · human request · language · "lėčiau" · "nesupratau")
             ─► RAG: LT-stemmed BM25 over cited public pages + shelter gazetteer + active incidents
             ─► LLM via LangChain (Gemini | Mistral | offline extractive mock)
             ─► LT normaliser + pronunciation lexicon
             ─► TTS (Google Cloud TTS | ElevenLabs | Gemini TTS | Azure* | Tilde* | mock) ─► caller
                                                     * stub adapters, disabled by default
```

## Why Lithuanian is the strong point

| Area | What is LT-specific |
|---|---|
| Prompts | `locales/lt/prompts.yaml` – Lithuanian system prompt tuned for phone answers (short, one action at a time, "Jūs" form, grounded-only, cite sources, 112 first). |
| Text normalisation for TTS | `locales/lt/normalize.py`, `numbers.py` – cardinals with **gender and case agreement** (`72 valandoms` → *septyniasdešimt dviem valandoms*, `8 metrus` → *aštuonis metrus*), ordinals for dates (`2026-11-20` → *…dvidešimt šeštųjų metų lapkričio dvidešimtoji*), clock times (`14:00` → *keturioliktą valandą*), units, decimals, ranges, **service numbers read digit-by-digit** (`112` → *vienas, vienas, du*; `1852` in phone context), house numbers (`245A`), abbreviations (`pvz.`, `t. y.`, `g.`, `sav.`) and URLs. Works the same for every TTS vendor. |
| Pronunciation lexicon | `locales/lt/lexicon.yaml` – acronyms and domains spoken as Lithuanian letters (`PAGD` → *pė a gė dė*, `lt72.lt`), with stress notes for review. |
| Retrieval | `locales/lt/stem.py` – light Lithuanian stemmer (case endings) + diacritic folding so *Žirmūnuose / Žirmūnų / Žirmūnai* and *priedangą / priedangos* match; colloquial → official query expansions (`dingo elektra` → *elektros tiekimo sutrikimai*). |
| Place understanding | `rag/places.py` – matches inflected eldership/municipality names to the PAGD shelter open data and confirms: *„Ar teisingai supratau – Žirmūnų seniūnija?“* |
| Safety rules | `profiles/civil-protection-lt/profile.yaml` – LT regexes for life-threatening situations (→ 112 + operator), requests for a human, slower/repeat, "nesupratau" (→ simpler rephrase), language ID with RU/UK/EN/PL hand-off messages. Never left to the LLM. |
| Evaluation | `profiles/civil-protection-lt/eval/lt_eval.yaml` – 18 LT questions with expected actions and answer points from the cited sources; `scripts/compare_providers.py` scores LLMs (action accuracy, point coverage, citations, LT-only, phone style, latency) and runs a TTS→(G.711)→STT round trip for WER/CER per voice/recogniser pair. |

## Quick start

```bash
uv venv .venv --python 3.13
uv pip install --python .venv/bin/python -r knowledge_line/requirements.txt
cp knowledge_line/.env.example .env      # fill in keys (optional – mocks work without)

.venv/bin/python -m knowledge_line.cli info
.venv/bin/python -m knowledge_line.cli ask "Kur man slėptis, jei paskelbtų oro pavojų? Gyvenu Žirmūnuose." --say out/answer.mp3
.venv/bin/python -m knowledge_line.cli listen question.wav --say out/answer.mp3
.venv/bin/python -m knowledge_line.cli chat
.venv/bin/python -m knowledge_line.cli normalize "Skambinkite 112, pasiruoškite 72 valandoms."
.venv/bin/python -m knowledge_line.web           # http://127.0.0.1:5055  (mic + text, /admin for incidents)
.venv/bin/python -m knowledge_line.scripts.demo --phone    # scripted calls -> knowledge_line/output/demo/*
.venv/bin/python -m knowledge_line.scripts.compare_providers --phone
.venv/bin/python -m knowledge_line.scripts.fetch_kb        # refresh KB pages + shelter open data
.venv/bin/python -m pytest knowledge_line/tests -q         # offline, mocks only
```

Provider selection: `--llm gemini|mistral|mock --stt elevenlabs|google|gemini|mock --tts google|elevenlabs|gemini|mock`
on every command, `KL_*_PROVIDER` env vars, or a YAML passed with `--config` / `KL_CONFIG`
(deep-merged over `configs/default.yaml`). `auto` picks the first provider in
`fallback_order` whose credentials are present.

## Profiles

A profile is data, not code: `profiles/<name>/{profile.yaml, sources.yaml, kb/*.md,
data/, eval/, demo_script.yaml}`. Service name, default municipality, safety patterns,
messages and sources are configurable, so the same engine serves other topics or
languages (add `locales/<lang>/`).

Knowledge-base pages keep their source URL, publisher and fetch date in front matter;
answers cite them. Some public sites sit behind bot challenges, so `fetch_kb` falls back
to an Internet Archive snapshot and otherwise keeps the committed verbatim excerpt.

## Limits (honest)

* Text/HTTP turn-based demo, not yet a streaming SIP/telephony loop (barge-in, DTMF).
  Wiring the providers into FastVoice's Pipecat pipeline is the next step.
* LT number normalisation covers nominative, accusative and dative agreement; other
  cases (genitive/instrumental after prepositions) fall back to nominative.
* WER/CER from the synthetic round trip is a proxy; real WER needs recorded human
  speakers (incl. 65+ and dialect speakers) over a real phone channel, and TTS quality
  needs a listener MOS test.
* Azure and Tilde adapters are stubs.
