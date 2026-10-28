"""Generador de Webhook URL + receptor + página de conteo de personas.
Sin dependencias (solo librería estándar). Requiere Python 3.8+.
Uso desde la terminal:  python server.py
"""
import json
import os
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("PORT", 3000))
try:
    BASE = os.path.dirname(os.path.abspath(__file__))
except NameError:  # Jupyter / notebook: no existe __file__
    BASE = os.getcwd()
FILE = os.path.join(os.environ.get("DATA_DIR", BASE), "data.json")
lock = threading.Lock()

try:
    with open(FILE, encoding="utf-8") as f:
        db = json.load(f)
except Exception:
    db = {}


def save():
    try:
        with open(FILE, "w", encoding="utf-8") as f:
            json.dump(db, f)
    except Exception:
        pass


# Busca el conteo dentro de cualquier JSON que envíe Lumeo.
KEYS = ["people_count", "count", "current_objects_count", "objects_count", "total_count", "total"]


def find_count(o, depth=0):
    if not isinstance(o, (dict, list)) or depth > 6:
        return None
    items = o.values() if isinstance(o, dict) else o
    if isinstance(o, dict):
        for k in KEYS:
            v = o.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return v
    for v in items:
        r = find_count(v, depth + 1)
        if r is not None:
            return r
    return None


CSS = """
:root{--bg:#eef2ef;--ink:#12302f;--mute:#5d726f;--line:#cbd8d4;--acc:#0b7a6b;--card:#fbfdfc}
@media(prefers-color-scheme:dark){:root{--bg:#0f1b1a;--ink:#e3efec;--mute:#8aa39f;--line:#274240;--acc:#3fd0b8;--card:#142826}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;padding:max(20px,env(safe-area-inset-top)) 20px 40px}
main{max-width:640px;margin:0 auto}h1{font-size:1.1rem;font-weight:600;margin:8px 0 24px}
button,.btn{font:inherit;background:var(--acc);color:#fff;border:0;border-radius:8px;padding:10px 16px;cursor:pointer;text-decoration:none;display:inline-block}
button.sec{background:transparent;color:var(--ink);border:1px solid var(--line)}
button:focus-visible,a:focus-visible{outline:3px solid var(--acc);outline-offset:2px}
code,input{font:14px ui-monospace,Menlo,Consolas,monospace}
.url{display:flex;gap:8px;margin:8px 0 20px}.url input{flex:1;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);min-width:0}
p{color:var(--mute);margin:6px 0}a{color:var(--acc)}
"""

HOME = """<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Generador de Webhook URL</title><style>__CSS__</style>
<main><h1>Generador de Webhook URL para conteo de personas</h1>
<p>Crea una URL única para pegarla en el nodo Webhook de Lumeo. Cada URL tiene su propia página de conteo.</p>
<p><button id="gen">Generar URL</button></p>
<div id="salida" hidden>
<p>Webhook URL (pégala en Lumeo)</p><div class="url"><input id="wh" readonly><button class="sec" data-c="wh">Copiar</button></div>
<p>Página de conteo</p><div class="url"><input id="pg" readonly><button class="sec" data-c="pg">Copiar</button></div>
<a class="btn" id="abrir" target="_blank" rel="noopener">Abrir página de conteo</a>
<p style="margin-top:20px">Si Lumeo envía un evento por cada persona que cruza una línea (sin un campo de conteo), agrega <code>?modo=evento</code> al final de la Webhook URL: cada llamada suma 1.</p></div></main>
<script>
const $=id=>document.getElementById(id);
$('gen').onclick=async()=>{const r=await (await fetch('/api/nuevo',{method:'POST'})).json();
$('wh').value=r.webhook;$('pg').value=r.pagina;$('abrir').href=r.pagina;$('salida').hidden=false};
document.addEventListener('click',ev=>{const k=ev.target.dataset.c;if(k){const i=$(k);i.select();navigator.clipboard&&navigator.clipboard.writeText(i.value);ev.target.textContent='Copiado';setTimeout(()=>ev.target.textContent='Copiar',1500)}});
</script></html>"""

PAGE = """<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Conteo de personas</title><style>__CSS__
.n{font-size:clamp(5rem,28vw,11rem);font-weight:700;line-height:1;font-variant-numeric:tabular-nums;letter-spacing:-.03em;margin:4px 0 0}
.meta{display:flex;gap:24px;flex-wrap:wrap}svg{width:100%;height:90px;margin:16px 0;border-bottom:1px solid var(--line)}
pre{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;overflow:auto;max-height:220px;font-size:13px}</style>
<main><h1>Personas contadas</h1>
<div class="n" id="n" aria-live="polite">–</div>
<div class="meta"><p>Eventos recibidos: <b id="ev">0</b></p><p>Última actualización: <b id="ult">sin datos</b></p></div>
<svg id="graf" viewBox="0 0 300 90" preserveAspectRatio="none" aria-hidden="true"></svg>
<p><button class="sec" id="reset">Reiniciar a 0</button></p>
<p>Último dato recibido de Lumeo (útil para verificar el formato):</p><pre id="json">Esperando el primer evento…</pre></main>
<script>
const ID=__ID__;const $=id=>document.getElementById(id);
async function tick(){try{const d=await (await fetch('/api/'+ID)).json();
$('n').textContent=d.count;$('ev').textContent=d.events;$('ult').textContent=d.last?new Date(d.last).toLocaleTimeString():'sin datos';
if(d.payload!==null)$('json').textContent=JSON.stringify(d.payload,null,2);
const h=d.history;if(h.length>1){const m=Math.max(...h.map(x=>x[1]),1);
$('graf').innerHTML='<polyline fill="none" stroke="var(--acc)" stroke-width="2" vector-effect="non-scaling-stroke" points="'+h.map((x,i)=>(i/(h.length-1)*300).toFixed(1)+','+(86-x[1]/m*80).toFixed(1)).join(' ')+'"/>'}}catch(_){}}
$('reset').onclick=async()=>{await fetch('/api/'+ID+'/reset',{method:'POST'});tick()};
tick();setInterval(tick,2000);
</script></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silencia el log por petición
        pass

    def origin(self):
        proto = self.headers.get("X-Forwarded-Proto", "http")
        return f"{proto}://{self.headers.get('Host')}"

    def send(self, code, body, ctype="application/json"):
        data = (body if isinstance(body, str) else json.dumps(body)).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def route(self, method):
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        qs = parse_qs(url.query)

        if method == "GET" and not parts:
            return self.send(200, HOME.replace("__CSS__", CSS), "text/html")

        if method == "POST" and url.path == "/api/nuevo":
            sid = secrets.token_hex(6)
            with lock:
                db[sid] = {"created": int(time.time() * 1000), "count": 0, "events": 0,
                           "last": None, "payload": None, "history": []}
                save()
            o = self.origin()
            return self.send(200, {"id": sid, "webhook": f"{o}/hook/{sid}", "pagina": f"{o}/c/{sid}"})

        if len(parts) >= 2 and parts[1] in db:
            sid, s = parts[1], db[parts[1]]

            if parts[0] == "c" and method == "GET":
                page = PAGE.replace("__CSS__", CSS).replace("__ID__", json.dumps(sid))
                return self.send(200, page, "text/html")

            if parts[0] == "api":
                if method == "GET" and len(parts) == 2:
                    return self.send(200, s)
                if method == "POST" and len(parts) == 3 and parts[2] == "reset":
                    with lock:
                        s["count"], s["history"] = 0, []
                        save()
                    return self.send(200, {"ok": True})

            if parts[0] == "hook" and method in ("POST", "PUT", "GET"):
                n = min(int(self.headers.get("Content-Length") or 0), 1_000_000)
                raw = self.rfile.read(n).decode("utf-8", "replace") if n else ""
                try:
                    body = json.loads(raw) if raw else {k: v[0] for k, v in qs.items()}
                except ValueError:
                    body = {"raw": raw[:2000]}
                found = None if qs.get("modo") == ["evento"] else find_count(body)
                with lock:
                    s["count"] = found if found is not None else s["count"] + 1
                    s["events"] += 1
                    s["last"] = int(time.time() * 1000)
                    s["payload"] = body
                    s["history"].append([s["last"], s["count"]])
                    s["history"] = s["history"][-200:]
                    save()
                return self.send(200, {"ok": True, "count": s["count"]})

        self.send(404, {"error": "No encontrado"})

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_PUT(self):
        self.route("PUT")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Listo en http://localhost:{PORT}")
    if "ipykernel" in sys.modules:
        # En Jupyter el servidor corre en segundo plano y la celda no se bloquea.
        threading.Thread(target=server.serve_forever, daemon=True).start()
    else:
        server.serve_forever()
