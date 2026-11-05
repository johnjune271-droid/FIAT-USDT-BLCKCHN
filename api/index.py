from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import os, json

app = FastAPI()

def get_kv():
    try:
        import redis
        r = redis.from_url(os.getenv("KV_URL"), decode_responses=True, socket_connect_timeout=3)
        r.ping()
        return r
    except Exception as e:
        print(f"KV ERROR: {e}")
        return None

def get_wallets():
    kv = get_kv()
    if kv:
        try:
            data = kv.get("cipher:wallets")
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"GET ERROR: {e}")
    return []

def save_wallets(wallets):
    kv = get_kv()
    if not kv:
        return False, "No KV connection"
    try:
        kv.set("cipher:wallets", json.dumps(wallets))
        return True, "Saved"
    except Exception as e:
        return False, str(e)

@app.get("/")
def root():
    kv = get_kv()
    w = get_wallets()
    return {"status":"ok","redis":bool(kv),"wallets_count":len(w),"total_percent":sum(x.get("percent",0) for x in w)}

@app.get("/api/admin/wallets")
def api_get():
    return {"wallets": get_wallets(), "redis": bool(get_kv())}

@app.post("/api/admin/wallets")
async def api_save(request: Request):
    try:
        body = await request.json()
        wallets = body.get("wallets", [])
        # Clean
        clean = []
        for w in wallets:
            addr = w.get("address","").strip()
            if addr:
                clean.append({"address": addr, "percent": float(w.get("percent",0))})
        
        ok, msg = save_wallets(clean)
        if ok:
            return {"status":"saved", "wallets": clean, "total": sum(x["percent"] for x in clean), "message": msg}
        else:
            return {"status":"error", "message": msg}
    except Exception as e:
        return {"status":"error","message":str(e)}

@app.post("/api/distribute")
async def dist(request: Request):
    body = await request.json()
    amt = float(body.get("amount",0))
    w = get_wallets()
    payouts = [{"address":x["address"],"percent":x["percent"],"payout":amt*x["percent"]/100} for x in w]
    return {"amount":amt,"total_percent":sum(x["percent"] for x in w),"payouts":payouts}

@app.get("/admin")
def admin():
    return HTMLResponse("""
<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>CIPHER ADMIN - WORKING</title>
<style>
body{background:#000;color:#0f0;font-family:monospace;padding:15px}
.card{border:2px solid #0f0;padding:20px;margin:10px 0;border-radius:10px;background:#111}
input{background:#000;color:#0f0;border:1px solid #0f0;padding:10px;width:100%;margin:5px 0}
.row{display:flex;gap:10px;margin:8px 0}
.row input:first-child{flex:1}
.row input:nth-child(2){width:80px}
button{background:#0f0;color:#000;border:none;padding:12px 20px;font-weight:bold;cursor:pointer;border-radius:5px;margin:5px}
.btn-red{background:#f00;color:#fff}
#total{font-size:24px;color:yellow;text-align:center;padding:15px;border:2px solid yellow;margin:15px 0}
pre{background:#000;padding:10px;overflow:auto;border:1px solid #333}
</style></head>
<body>
<h1>🔧 CIPHER-JOHN ADMIN - FUNCTIONAL</h1>

<div class="card">
<h2>Wallet Setup</h2>
<div id="list"></div>
<button onclick="add()">+ Add Wallet</button>
<div id="total">Total: 0%</div>
<button onclick="save()" style="width:100%;font-size:18px">💾 SAVE TO KV (Redis)</button>
<div id="msg"></div>
</div>

<div class="card">
<h2>Test</h2>
<input type="number" id="amt" value="100">
<button onclick="testDist()">Calculate Distribution for $<span id="amtLabel">100</span></button>
<pre id="out">Click Calculate...</pre>
</div>

<script>
let wallets = [];
async function load(){
  const r = await fetch('/api/admin/wallets');
  const j = await r.json();
  wallets = j.wallets || [];
  if(wallets.length==0){ wallets = [{address:"",percent:10},{address:"",percent:10},{address:"",percent:10},{address:"",percent:10},{address:"",percent:10}]; }
  render();
}
function render(){
  const d = document.getElementById('list');
  d.innerHTML='';
  wallets.forEach((w,i)=>{
    const row = document.createElement('div');
    row.className='row';
    row.innerHTML = `<input value="${w.address}" placeholder="0x or T address" oninput="wallets[${i}].address=this.value"><input type="number" value="${w.percent}" oninput="wallets[${i}].percent=parseFloat(this.value)||0;update()"><button class="btn-red" onclick="wallets.splice(${i},1);render()">X</button>`;
    d.appendChild(row);
  });
  update();
}
function add(){ wallets.push({address:"",percent:10}); render(); }
function update(){ const t = wallets.reduce((s,w)=>s+(parseFloat(w.percent)||0),0); document.getElementById('total').innerText='Total: '+t+'%'; document.getElementById('amtLabel').innerText=document.getElementById('amt').value; }

async function save(){
  document.getElementById('msg').innerHTML='Saving...';
  const res = await fetch('/api/admin/wallets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({wallets})});
  const data = await res.json();
  document.getElementById('msg').innerHTML='<pre>'+JSON.stringify(data,null,2)+'</pre>';
  if(data.status=='saved'){ alert('SAVED! '+data.total+'%'); }
  else{ alert('ERROR: '+data.message); }
}
async function testDist(){
  const amt = document.getElementById('amt').value;
  const res = await fetch('/api/distribute',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({amount:parseFloat(amt)})});
  const data = await res.json();
  document.getElementById('out').innerText=JSON.stringify(data,null,2);
}
load();
document.getElementById('amt').addEventListener('input',update);
</script>
</body></html>
    """)