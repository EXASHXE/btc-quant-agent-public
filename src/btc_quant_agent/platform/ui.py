"""Optional localhost dashboard for the offline CLI/report contracts."""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import PlatformConfig
from .reporting import document


def page():
    return document(
        "Quant local synthetic workbench",
        """<p>Select independent strategies and factors. All results use generated fixtures.</p>
    <label>Market <select id="market"><option>PERPETUAL</option><option>SPOT</option><option>EQUITY</option><option>ETF</option></select></label>
    <label>Scenario <select id="scenario"><option>mixed</option><option>trend</option><option>range</option><option>shock</option></select></label>
    <p><label>Strategies <select id="strategies" multiple size="8"></select></label>
    <label>Factors <select id="factors" multiple size="8"></select></label></p>
    <label>Risk fraction <input id="risk" type="number" step=".001" value=".005"></label>
    <label>Slippage bps <input id="slip" type="number" value="2"></label>
    <label>Stop lookback <input id="lookback" type="number" value="12"></label>
    <p><label>Factor weights / parameters (JSON) <textarea id="weights" rows="3" cols="75">{}</textarea></label></p>
    <button id="run">Run synthetic replay</button><button id="models">Inspect model artifacts</button>
    <p id="status" role="status"></p><div id="link"></div><pre id="result"></pre>
    <script>
    const get=id=>document.getElementById(id);
    fetch('/api/catalog').then(r=>r.json()).then(c=>{
      for(const [key,items] of Object.entries(c))for(const id of items){let o=new Option(id,id);get(key).add(o);}
      get('strategies').value='trend_breakout';
    });
    get('run').onclick=async()=>{get('status').textContent='Running synthetic replay…';
      try{const custom=JSON.parse(get('weights').value);
        const config={market:get('market').value,scenario:get('scenario').value,
          strategies:[...get('strategies').selectedOptions].map(o=>({id:o.value})),
          factors:[...get('factors').selectedOptions].map(o=>({id:o.value,...(custom[o.value]||{})})),
          risk:{per_trade:Number(get('risk').value)},execution:{slippage_bps:Number(get('slip').value)},
          exits:{stop_lookback:Number(get('lookback').value)}};
        const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json','X-Quant-Local':'1'},body:JSON.stringify(config)});
        const data=await r.json();get('result').textContent=JSON.stringify(data,null,2);get('link').replaceChildren();
        if(data.run_id){let a=document.createElement('a');a.href='/report?id='+data.run_id;a.textContent='Open detailed report';get('link').append(a);}
        get('status').textContent=r.ok?'Completed · SYNTHETIC':'Validation failed';
      }catch(e){get('status').textContent=String(e);}};
    get('models').onclick=async()=>get('result').textContent=JSON.stringify(await(await fetch('/api/models')).json(),null,2);
    </script>""",
    )


def serve(port=8765):
    root = Path(__file__).resolve().parents[3]
    artifact_root = root / "artifacts/ui_runs"

    class Handler(BaseHTTPRequestHandler):
        def reply(self, value, status=200, kind="application/json"):
            data = (json.dumps(value, allow_nan=False) if kind == "application/json" else value).encode()
            self.send_response(status)
            self.send_header("Content-Type", kind + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            route = urlparse(self.path)
            if route.path == "/":
                return self.reply(page(), kind="text/html")
            if route.path == "/api/catalog":
                from .factors import REGISTRY as factors
                from .strategies import REGISTRY as strategies

                return self.reply(
                    {
                        "strategies": [id for id, v in strategies.items() if v.status != "RESEARCH_ONLY"],
                        "factors": list(factors),
                    }
                )
            if route.path == "/api/models":
                from .ml import ModelRegistry

                return self.reply(ModelRegistry(root / "artifacts/models").list())
            if route.path == "/report":
                id = parse_qs(route.query).get("id", [""])[0]
                if not re.fullmatch("[a-f0-9]{64}", id):
                    return self.reply({"error": "invalid run id"}, 400)
                path = artifact_root / id / "report.html"
                if path.is_file():
                    return self.reply(path.read_text(), kind="text/html")
            return self.reply({"error": "not found"}, 404)

        def do_POST(self):
            if self.path != "/api/run":
                return self.reply({"error": "not found"}, 404)
            if self.headers.get("X-Quant-Local") != "1":
                return self.reply({"error": "local request header required"}, 403)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    raise ValueError("request size invalid")
                config = PlatformConfig.model_validate(json.loads(self.rfile.read(length)))
                from .backtest import run
                from .reporting import save_run, source_identity

                result = run(config, source_hash=source_identity())
                save_run(result, artifact_root)
                return self.reply({"run_id": result["run"]["run_id"], "metrics": result["run"]["metrics"]})
            except (ValueError, KeyError) as exc:
                return self.reply({"error": str(exc)}, 400)

        def log_message(self, format, *args):
            return

    print(f"Local synthetic dashboard: http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
