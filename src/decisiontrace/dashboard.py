"""Zero-dependency web dashboard: timeline replay, explanations, anomalies."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .drift import detect
from .explain import explain
from .storage import Store

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>DecisionTrace</title>
<style>
:root{--bg:#f6f6f3;--card:#fff;--fg:#1d1d1f;--mut:#6b6b70;--bd:#e2e2dd;--ok:#1a7f4b;--warn:#b7791f;--bad:#c53030;--acc:#3b5bdb}
@media(prefers-color-scheme:dark){:root{--bg:#141416;--card:#1e1e22;--fg:#ececee;--mut:#9a9aa2;--bd:#2e2e34;--ok:#4cc38a;--warn:#e0b04a;--bad:#f06a6a;--acc:#8aa0ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,sans-serif}
header{padding:14px 20px;border-bottom:1px solid var(--bd);background:var(--card);display:flex;gap:10px;align-items:baseline}
header h1{font-size:17px;margin:0}header span{color:var(--mut)}
#stats{display:flex;gap:10px;padding:14px 20px;flex-wrap:wrap}
.stat{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:10px 16px;min-width:120px}
.stat b{display:block;font-size:22px}.stat span,.muted{color:var(--mut);font-size:12px}
#anoms{padding:0 20px}.anom{background:var(--card);border:1px solid var(--bad);color:var(--bad);border-radius:8px;padding:6px 10px;margin-bottom:6px}
main{display:grid;grid-template-columns:340px 1fr;gap:14px;padding:14px 20px}
@media(max-width:800px){main{grid-template-columns:1fr}}
#list,#detail{background:var(--card);border:1px solid var(--bd);border-radius:10px;overflow:auto;max-height:72vh}
.item{padding:10px 12px;border-bottom:1px solid var(--bd);cursor:pointer}.item:hover,.item.sel{background:var(--bg)}
.badge{font-size:11px;padding:1px 7px;border-radius:99px;border:1px solid var(--bd)}
.halted,.blocked{color:var(--bad);border-color:var(--bad)}.completed,.ok,.approved{color:var(--ok)}.pending_approval{color:var(--warn);border-color:var(--warn)}
#detail{padding:14px}.step{border-left:3px solid var(--bd);padding:4px 0 10px 12px;margin-left:6px}
.step.blocked{border-color:var(--bad)}.step.pending_approval{border-color:var(--warn)}
.viol{background:var(--bg);border-radius:6px;padding:4px 8px;margin-top:4px;font-size:12px}
pre{background:var(--bg);padding:8px;border-radius:6px;overflow:auto;font-size:12px;margin:4px 0;white-space:pre-wrap}
.explain{background:var(--bg);border-radius:8px;padding:10px;margin-bottom:14px;white-space:pre-wrap;font-size:13px}
</style></head><body>
<header><h1>DecisionTrace</h1><span>flight recorder for AI agents</span></header>
<div id="stats"></div><div id="anoms"></div>
<main><div id="list"></div><div id="detail"><span class="muted">Select a trace</span></div></main>
<script>
const $=s=>document.querySelector(s);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const j=async u=>(await fetch(u)).json();
const pre=x=>x==null?'':`<pre>${esc(JSON.stringify(x,null,1))}</pre>`;
async function init(){
  const s=await j('/api/summary');
  $('#stats').innerHTML=[['Traces',s.traces],['Steps',s.steps],['Policy hits',s.violations],['Stopped actions',s.blocked],['Cost (USD)',s.cost_usd.toFixed(4)]]
    .map(([k,v])=>`<div class="stat"><b>${esc(v)}</b><span>${k}</span></div>`).join('');
  const an=await j('/api/anomalies');
  $('#anoms').innerHTML=an.map(a=>`<div class="anom">Anomaly - ${esc(a.agent)}: ${esc(a.message)}</div>`).join('');
  const ts=await j('/api/traces');
  $('#list').innerHTML=ts.map(t=>`<div class="item" data-id="${esc(t.id)}"><div><b>${esc(t.agent)}</b> <span class="badge ${esc(t.status)}">${esc(t.status)}</span></div>
    <div>${esc(t.goal)}</div><div class="muted">${t.steps} steps - ${t.violations} policy hits - $${t.cost_usd}</div></div>`).join('');
  document.querySelectorAll('.item').forEach(e=>e.onclick=()=>show(e.dataset.id));
  if(ts.length) show(ts[0].id);
}
async function show(id){
  document.querySelectorAll('.item').forEach(e=>e.classList.toggle('sel',e.dataset.id===id));
  const [t,ex]=await Promise.all([j('/api/traces/'+id),j('/api/traces/'+id+'/explain')]);
  $('#detail').innerHTML=`<h3 style="margin-top:0">${esc(t.goal)}</h3><div class="explain">${esc(ex.text)}</div>`+
   t.steps.map(s=>`<div class="step ${esc(s.status)}"><b>${s.idx+1}. ${esc(s.type)}</b> - ${esc(s.name)}
     <span class="badge ${esc(s.status)}">${esc(s.status)}</span> ${s.pii.length?`<span class="badge warn">PII: ${esc(s.pii.join(', '))}</span>`:''}
     ${s.violations.map(v=>`<div class="viol"><b>${esc(v.action)}</b> - ${esc(v.rule_id)}: ${esc(v.message)}</div>`).join('')}
     ${pre(s.input)}${pre(s.output)}</div>`).join('');
}
init();
</script></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    store: Store = None  # set per server

    def log_message(self, *args):  # keep the console quiet
        pass

    def _send(self, code: int, body, ctype: str = "application/json") -> None:
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parts = [p for p in urlparse(self.path).path.split("/") if p]
        s = self.store
        if not parts:
            return self._send(200, PAGE, "text/html")
        if parts[0] != "api" or len(parts) < 2:
            return self._send(404, json.dumps({"error": "not found"}))
        if parts[1] == "summary":
            return self._send(200, json.dumps(s.summary()))
        if parts[1] == "anomalies":
            return self._send(200, json.dumps([a for ag in s.agents() for a in detect(s, ag)]))
        if parts[1] == "traces" and len(parts) == 2:
            return self._send(200, json.dumps(s.list_traces()))
        if parts[1] == "traces" and len(parts) in (3, 4):
            trace = s.get_trace(parts[2])
            if trace is None:
                return self._send(404, json.dumps({"error": "trace not found"}))
            if len(parts) == 4 and parts[3] == "explain":
                return self._send(200, json.dumps({"text": explain(trace)}))
            return self._send(200, json.dumps(trace))
        self._send(404, json.dumps({"error": "not found"}))


def make_server(store: Store, host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    handler = type("Handler", (_Handler,), {"store": store})
    return ThreadingHTTPServer((host, port), handler)


def serve(store: Store, host: str = "127.0.0.1", port: int = 8000) -> None:
    server = make_server(store, host, port)
    print(f"DecisionTrace dashboard running at http://{host}:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
