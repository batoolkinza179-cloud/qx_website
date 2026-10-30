import os
import time
import threading
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template_string
from tradingview_ta import TA_Handler, Interval

app = Flask(__name__)

PAIRS = {
    "EUR/USD": "EURUSD", "GBP/USD": "GBPUSD", "USD/JPY": "USDJPY",
    "USD/CHF": "USDCHF", "AUD/USD": "AUDUSD", "USD/CAD": "USDCAD",
    "NZD/USD": "NZDUSD",
}
BUY = ("BUY", "STRONG_BUY")
SELL = ("SELL", "STRONG_SELL")
REFRESH_SECONDS = 60

cache = {"rows": [], "updated": None}
lock = threading.Lock()


def analysis(symbol, interval):
    return TA_Handler(symbol=symbol, screener="forex",
                      exchange="FX_IDC", interval=interval).get_analysis()


def build_row(pair, symbol):
    a5 = analysis(symbol, Interval.INTERVAL_5_MINUTES)
    a15 = analysis(symbol, Interval.INTERVAL_15_MINUTES)
    r5 = a5.summary.get("RECOMMENDATION", "NEUTRAL")
    r15 = a15.summary.get("RECOMMENDATION", "NEUTRAL")
    ind = a5.indicators
    price, rsi = ind.get("close"), ind.get("RSI")
    macd, sig = ind.get("MACD.macd"), ind.get("MACD.signal")
    if None in (price, rsi, macd, sig):
        raise ValueError("indicators missing")
    signal = "WAIT"
    if r5 in BUY and r15 in BUY and 52 <= rsi <= 68 and macd > sig:
        signal = "CALL"
    elif r5 in SELL and r15 in SELL and 32 <= rsi <= 48 and macd < sig:
        signal = "PUT"
    return {"pair": pair, "price": round(price, 5), "rsi": round(rsi, 1),
            "m5": r5, "m15": r15, "signal": signal}


def refresher():
    while True:
        rows = []
        for pair, symbol in PAIRS.items():
            try:
                rows.append(build_row(pair, symbol))
            except Exception as exc:
                print(pair, "error:", repr(exc))
                rows.append({"pair": pair, "price": None, "rsi": None,
                             "m5": "N/A", "m15": "N/A", "signal": "N/A"})
            time.sleep(2)
        with lock:
            cache["rows"] = rows
            cache["updated"] = datetime.now(timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S UTC")
        time.sleep(REFRESH_SECONDS)


threading.Thread(target=refresher, daemon=True).start()

PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Forex Signals - TradingView Analysis</title>
<meta name="description" content="Live forex technical analysis (M5 and M15) for major pairs using TradingView data.">
<style>
:root{--bg:#f6f7f9;--card:#fff;--text:#14171c;--mut:#6b7280;--line:#e5e7eb;--g:#0a8f4d;--r:#c62828}
@media (prefers-color-scheme:dark){:root{--bg:#0f1216;--card:#181c22;--text:#eceff3;--mut:#9aa3af;--line:#272c34;--g:#34d27b;--r:#ff6b6b}}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,Arial,sans-serif;background:var(--bg);color:var(--text)}
.wrap{max-width:860px;margin:0 auto;padding:16px}
h1{font-size:1.4rem;margin:8px 0}
.sub{color:var(--mut);font-size:.9rem;margin-bottom:12px}
input{width:100%;padding:12px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--text);font-size:1rem;margin-bottom:12px}
.box{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:12px}
table{width:100%;border-collapse:collapse;min-width:520px}
th,td{padding:12px;text-align:left;border-bottom:1px solid var(--line);font-size:.95rem}
th{color:var(--mut);font-weight:600;font-size:.8rem}
tr:last-child td{border-bottom:0}
.CALL{color:var(--g);font-weight:700}.PUT{color:var(--r);font-weight:700}.WAIT,.N\\/A{color:var(--mut)}
.warn{margin-top:14px;font-size:.82rem;color:var(--mut);line-height:1.5}
</style></head><body><div class="wrap">
<h1>Forex Signals</h1>
<div class="sub">TradingView technical analysis, M5 + M15. <span id="upd">Loading...</span></div>
<input id="q" placeholder="Search pair, e.g. EUR/USD" autocomplete="off">
<div class="box"><table>
<thead><tr><th>Pair</th><th>Price</th><th>RSI</th><th>M5</th><th>M15</th><th>Signal</th></tr></thead>
<tbody id="rows"><tr><td colspan="6">Loading...</td></tr></tbody></table></div>
<p class="warn"><b>Disclaimer:</b> Educational information only, not financial advice and not a win probability.
Trading carries a high risk of losing money. Data comes from a public feed and may differ from your broker.
Always check the live chart yourself.</p>
</div>
<script>
let data=[];
function show(){
  const q=document.getElementById('q').value.trim().toLowerCase().replace('/','');
  const rows=data.filter(r=>r.pair.toLowerCase().replace('/','').includes(q));
  const tb=document.getElementById('rows');
  tb.innerHTML='';
  if(!rows.length){tb.innerHTML='<tr><td colspan="6">No data</td></tr>';return;}
  rows.forEach(r=>{
    const tr=document.createElement('tr');
    [r.pair,r.price??'-',r.rsi??'-',r.m5,r.m15,r.signal].forEach((v,i)=>{
      const td=document.createElement('td');td.textContent=v;
      if(i==5)td.className=r.signal;
      tr.appendChild(td);
    });
    tb.appendChild(tr);
  });
}
async function load(){
  try{
    const res=await fetch('/api/signals');const j=await res.json();
    data=j.rows;
    document.getElementById('upd').textContent=j.updated?('Updated '+j.updated):'Warming up, refresh in a minute...';
    show();
  }catch(e){document.getElementById('upd').textContent='Connection error';}
}
document.getElementById('q').addEventListener('input',show);
load();setInterval(load,30000);
</script></body></html>"""


@app.route("/")
def home():
    return render_template_string(PAGE)


@app.route("/api/signals")
def api():
    with lock:
        return jsonify(cache)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
