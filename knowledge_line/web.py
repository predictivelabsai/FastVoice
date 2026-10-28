"""Web demo (FastHTML, same stack as the FastVoice UI).

    python -m knowledge_line.web            # http://127.0.0.1:5055

Talk (browser microphone) or type in Lithuanian; the answer is spoken back.
/admin toggles incident status (an active incident is announced in the
greeting and used as priority context).
"""

from __future__ import annotations

import base64
import uuid
from functools import lru_cache

from fasthtml.common import (
    H1, H2, A, Audio, Button, Div, Form, Input, Label, Option, P, Script, Select, Span, Style, Table, Tbody, Td,
    Th, Thead, Title, Tr, fast_app, serve,
)
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import load_settings
from .incidents import STATUSES
from .llm import available_llm_providers
from .pipeline import Answer, KnowledgeLine, Session
from .speech import available_stt

SETTINGS = load_settings()
SESSIONS: dict[str, Session] = {}

CSS = """
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#1b1f24}
h1{font-size:1.5rem;margin-bottom:.2rem} .muted{color:#667085;font-size:.9rem}
.row{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin:.6rem 0}
input[type=text]{flex:1;padding:.6rem;border:1px solid #d0d5dd;border-radius:8px;font-size:1rem}
button{padding:.55rem .9rem;border-radius:8px;border:1px solid #d0d5dd;background:#fff;cursor:pointer;font-size:.95rem}
button.primary{background:#0b5fff;color:#fff;border-color:#0b5fff} button.rec{background:#d92d20;color:#fff;border-color:#d92d20}
#log{margin-top:1rem} .turn{border:1px solid #eaecf0;border-radius:10px;padding:.7rem .9rem;margin:.6rem 0}
.q{font-weight:600} .a{margin-top:.3rem;white-space:pre-wrap} .meta{color:#667085;font-size:.8rem;margin-top:.3rem}
.badge{display:inline-block;font-size:.75rem;padding:.1rem .45rem;border-radius:99px;background:#f2f4f7;margin-right:.3rem}
.badge.emergency_transfer{background:#fee4e2;color:#b42318}.badge.operator_transfer,.badge.language_transfer{background:#fef0c7;color:#93370d}
.badge.no_info{background:#f2f4f7}.badge.answer{background:#d1fadf;color:#05603a}
select{padding:.4rem;border-radius:6px} table{border-collapse:collapse;width:100%} td,th{border-bottom:1px solid #eaecf0;padding:.4rem;text-align:left;font-size:.9rem}
"""

JS = r"""
const sid = crypto.randomUUID();
function prov(){return {llm:document.getElementById('llm').value, tts:document.getElementById('tts').value, stt:document.getElementById('stt').value}}
function render(d, q){
  const a=d.answer; const log=document.getElementById('log');
  const el=document.createElement('div'); el.className='turn';
  const cites=(a.citations||[]).map(c=>`<a href="${c.url}" target="_blank">[${c.n}] ${c.title}</a>`).join(' · ');
  const lat=Object.entries(a.latency_ms||{}).map(([k,v])=>`${k}: ${v}`).join(', ');
  el.innerHTML=`<div class="q">🧑 ${(d.transcript?d.transcript.text:q)||''}</div>
   <div class="a"><span class="badge ${a.action}">${a.action}</span>${a.text}</div>
   <div class="meta">${cites}</div><div class="meta">⏱ ${lat} · ${a.llm||''} ${d.audio?('· TTS '+d.audio.provider+' '+d.audio.voice):''}${d.transcript?(' · STT '+d.transcript.provider):''}</div>`;
  if(d.audio_data){const au=document.createElement('audio');au.controls=true;au.autoplay=true;au.src=d.audio_data;el.appendChild(au);}
  log.prepend(el);
}
async function ask(q){
  if(!q) return; const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q,session_id:sid,...prov()})});
  render(await r.json(), q);
}
document.addEventListener('DOMContentLoaded',()=>{
  document.getElementById('askform').addEventListener('submit',e=>{e.preventDefault();const i=document.getElementById('q');ask(i.value);i.value='';});
  document.getElementById('slower').onclick=()=>ask('Pakartokite lėčiau');
  document.getElementById('greet').onclick=async()=>{const r=await fetch('/api/greeting?'+new URLSearchParams(prov()));render(await r.json(),'(skambutis pradėtas)');};
  let rec=null, chunks=[];
  const mic=document.getElementById('mic');
  mic.onclick=async()=>{
    if(rec&&rec.state==='recording'){rec.stop();mic.classList.remove('rec');mic.textContent='🎙 Kalbėti';return;}
    const stream=await navigator.mediaDevices.getUserMedia({audio:true});
    rec=new MediaRecorder(stream); chunks=[];
    rec.ondataavailable=e=>chunks.push(e.data);
    rec.onstop=async()=>{stream.getTracks().forEach(t=>t.stop());
      const blob=new Blob(chunks,{type:rec.mimeType||'audio/webm'}); const fd=new FormData();
      fd.append('audio',blob,'q.webm'); fd.append('session_id',sid); const p=prov(); for(const k in p) fd.append(k,p[k]);
      const r=await fetch('/api/listen',{method:'POST',body:fd}); render(await r.json(),'');};
    rec.start(); mic.classList.add('rec'); mic.textContent='⏹ Baigti';
  };
});
"""


@lru_cache(maxsize=16)
def pipeline(llm: str = "", stt: str = "", tts: str = "") -> KnowledgeLine:
    return KnowledgeLine(SETTINGS, llm_provider=llm or None, stt_provider=stt or None, tts_provider=tts or None)


def _payload(res) -> dict:
    d = res.to_dict()
    if res.audio:
        d["audio_data"] = f"data:{res.audio.mime};base64," + base64.b64encode(res.audio.audio).decode()
    return d


app, rt = fast_app(pico=False, hdrs=(Style(CSS),))


def _select(name: str, options: list[str]):
    return Select(*[Option(o or "auto", value=o) for o in ["", *options]], id=name, name=name)


@rt("/")
def index():
    kl = pipeline()
    info = kl.describe()
    stt_opts = [p for p in available_stt(SETTINGS)]
    return Title("FastVoice Knowledge Line"), Div(
        H1("FastVoice Knowledge Line"),
        P(f"Profilis: {info['profile']} · kalba: {info['locale']} · žinių bazė: {info['kb_chunks']} fragmentų · "
          f"priedangų įrašų: {info['shelters']}", cls="muted"),
        Div(Label("LLM ", _select("llm", available_llm_providers())), Label(" STT ", _select("stt", stt_opts)),
            Label(" TTS ", _select("tts", stt_opts)), Span(f"numatyta: {info['llm']} / {info['stt']} / {info['tts']}",
                                                            cls="muted"), cls="row"),
        Div(Button("📞 Pradėti skambutį", id="greet"), Button("🎙 Kalbėti", id="mic", cls="primary"),
            Button("🐢 Lėčiau", id="slower"), A("Administravimas →", href="/admin"), cls="row"),
        Form(Input(type="text", id="q", placeholder="Užduokite klausimą lietuviškai, pvz.: Kur slėptis per oro pavojų?"),
             Button("Klausti", type="submit", cls="primary"), id="askform", cls="row"),
        Div(id="log"),
        Script(JS),
    )


@rt("/api/ask", methods=["post"])
async def api_ask(request: Request):
    body = await request.json()
    sid = body.get("session_id") or str(uuid.uuid4())
    kl = pipeline(body.get("llm", ""), body.get("stt", ""), body.get("tts", ""))
    res = kl.turn_text(body.get("question", ""), SESSIONS.setdefault(sid, Session()), with_audio=True)
    return JSONResponse(_payload(res))


@rt("/api/listen", methods=["post"])
async def api_listen(request: Request):
    form = await request.form()
    up = form["audio"]
    data = await up.read()
    sid = form.get("session_id") or str(uuid.uuid4())
    kl = pipeline(form.get("llm", ""), form.get("stt", ""), form.get("tts", ""))
    res = kl.turn_audio(data, mime=(up.content_type or "audio/webm").split(";")[0],
                        session=SESSIONS.setdefault(sid, Session()), with_audio=True)
    return JSONResponse(_payload(res))


@rt("/api/greeting")
def api_greeting(llm: str = "", stt: str = "", tts: str = ""):
    from .pipeline import TurnResult

    kl = pipeline(llm, stt, tts)
    text = kl.greeting()
    ans = Answer(text=text, action="greeting", spoken_text=kl.speakable(text))
    return JSONResponse(_payload(TurnResult(answer=ans, audio=kl.speak(ans))))


@rt("/api/info")
def api_info():
    return JSONResponse(pipeline().describe())


def _incident_rows():
    rows = []
    for it in pipeline().incidents.load():
        btns = [Button(s, hx_post=f"/admin/incidents/{it['id']}/{s}", hx_target="#incidents", hx_swap="outerHTML",
                       disabled=it.get("status") == s) for s in STATUSES]
        rows.append(Tr(Td(it["title"]), Td(it.get("area", "")), Td(Span(it.get("status", ""), cls="badge")), Td(*btns)))
    return Table(Thead(Tr(Th("Incidentas"), Th("Teritorija"), Th("Statusas"), Th("Keisti"))), Tbody(*rows), id="incidents")


@rt("/admin")
def admin():
    return Title("Administravimas"), Div(
        H1("Administravimas"), A("← Atgal", href="/"),
        H2("Incidentai"),
        P("Aktyvus incidentas iškart paminimas kito skambučio pasisveikinime ir naudojamas kaip prioritetinis šaltinis.",
          cls="muted"),
        _incident_rows(), Script(src="https://unpkg.com/htmx.org@1.9.12"),
    )


@rt("/admin/incidents/{iid}/{status}", methods=["post"])
def set_status(iid: str, status: str):
    pipeline().incidents.set_status(iid, status)
    return _incident_rows()


def main():
    serve(appname="knowledge_line.web", app="app", host=str(SETTINGS.get("web.host", "127.0.0.1")),
          port=int(SETTINGS.get("web.port", 5055)), reload=False)


if __name__ == "__main__":
    main()
