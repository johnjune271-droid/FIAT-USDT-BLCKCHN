from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import os, json

app = FastAPI()
KV_PREFIX = "cipher:"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "cipher123")  # Set in Vercel Env

def get_kv():
    try:
        import redis
        r = redis.from_url(os.getenv("KV_URL"), decode_responses=True, socket_connect_timeout=3)
        r.ping()
        return r
    except:
        return None

def get_wallets():
    kv = get_kv()
    if kv:
        data = kv.get(f"{KV_PREFIX}wallets")
        if data:
            try: return json.loads(data)
            except: pass
    return []

def save_wallets(wallets):
    kv = get_kv()
    if kv:
        kv.set(f"{KV_PREFIX}wallets", json.dumps(wallets))
        return True
    return False

@app.get("/")
def root():
    kv = get_kv()
    w = get_wallets()
    return {"status":"ok","redis":bool(kv),"admin":"/admin","wallets":len(w),"total_%":sum(x.get("percent",0) for x in w)}

@app.get("/api/admin/wallets")
def get_w():
    return {"wallets": get_wallets()}

@app.post("/api/admin/wallets")
async def save_w(request: Request):
    body = await request.json()
    if body.get("password") != ADMIN_PASSWORD:
        return JSONResponse({"error":"Wrong password"}, status_code=401)
    wallets = body.get("wallets", [])
    save_wallets(wallets)
    return {"status":"saved","total":sum(x.get("percent",0) for x in wallets)}

@app.post("/api/distribute")
async def dist(request: Request):
    body = await request.json()
    amount = float(body.get("amount",0))
    wallets = get_wallets()
    results = [{"address":w["address"],"percent":w["percent"],"amount":amount*w["percent"]/100} for w in wallets]
    return {"input":amount,"total_percent":sum(w["percent"] for w in wallets),"payouts":results}

@app.get("/admin")
def admin():
    html = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CIPHER-JOHN Admin Panel</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#050505;color:#e0ffe0;font-family: 'Courier New', monospace;}
.header{background:#00ff88;color:#000;padding:15px 20px;display:flex;justify-content:space-between;align-items:center}
.header h1{margin:0;font-size:18px}
.container{max-width:900px;margin:20px auto;padding:0 15px}
.card{background:#111;border:1px solid #222;border-radius:12px;padding:20px;margin-bottom:20px}
.card h2{margin-top:0;color:#00ff88;border-bottom:1px solid #222;padding-bottom:10px}
input{width:100%;background:#000;color:#0f0;border:1px solid #333;padding:12px;border-radius:8px;margin:5px 0;font-family:monospace}
.row{display:grid;grid-template-columns:1fr 100px 50px;gap:10px;align-items:center;background:#1a1a1a;padding:10px;border-radius:8px;margin:8px 0}
.btn{background:#00ff88;color:#000;border:none;padding:12px 20px;border-radius:8px;font-weight:bold;cursor:pointer;width:100%;margin-top:10px}
.btn-red{background:#ff2040;color:#fff;width:auto;padding:8px 15px}
.btn-outline{background:transparent;border:1px solid #00ff88;color:#00ff88}
.total{font-size:28px;text-align:center;padding:20px;background:#000;border-radius:10px;border:2px solid #00ff88;margin:15px 0}
.login{max-width:400px;margin:100px auto;text-align:center}
.hidden{display:none}
</style>
</head>
<body>
<div class="header"><h1>🔐 CIPHER-JOHN FIAT-USDT-BLCKCHN</h1><span id="status">Redis: ✓</span></div>

<div id="loginPage" class="login card">
<h2>Admin Login</h2>
<input type="password" id="pwd" placeholder="Admin Password (default: cipher123)">
<button class="btn" onclick="login()">Login</button>
<p style="font-size:12px;color:#666">Set ADMIN_PASSWORD in Vercel Env to change</p>
</div>

<div id="mainPage" class="container hidden">
<div class="card">
<h2>💼 Wallet Distribution Control</h2>
<p style="color:#888">Admin decides how many wallets and what % each gets. Example: 5 wallets x 10% = 50% total distribution.</p>
<div id="walletList"></div>
<button class="btn-outline btn" onclick="addWallet()">+ Add New Wallet</button>
<div class="total" id="totalBox">Total: 0%</div>
<input type="password" id="savePwd" placeholder="Enter password to save">
<button class="btn" onclick="saveAll()">💾 SAVE TO BLOCKCHAIN KV</button>
<div id="saveResult"></div>
</div>

<div class="card">
<h2>🧪 Test Distribution</h2>
<input type="number" id="testAmount" value="100" placeholder="Amount to distribute">
<button class="btn btn-outline" onclick="test()">Test Calculate $100</button>
<pre id="testResult" style="background:#000;padding:15px;border-radius:8px;overflow:auto"></pre>
</div>
</div>

<script>
let wallets = [];
let adminPwd = "";

async function loadWallets(){
  const r = await fetch('/api/admin/wallets');
  const j = await r.json();
  wallets = j.wallets || [];
  render();
}

function login(){
  adminPwd = document.getElementById('pwd').value;
  if(!adminPwd){alert('Enter password');return}
  document.getElementById('loginPage').classList.add('hidden');
  document.getElementById('mainPage').classList.remove('hidden');
  document.getElementById('savePwd').value = adminPwd;
  loadWallets();
}

function render(){
  const c = document.getElementById('walletList');
  c.innerHTML = '';
  wallets.forEach((w,i)=>{
    const d = document.createElement('div');
    d.className='row';
    d.innerHTML = `<input value="${w.address||''}" placeholder="0x... ETH or TNmx... TRON" oninput="wallets[${i}].address=this.value">
    <input type="number" value="${w.percent||0}" placeholder="%" oninput="wallets[${i}].percent=parseFloat(this.value)||0; updateTotal()">
    <button class="btn-red" onclick="wallets.splice(${i},1);render()">✕</button>`;
    c.appendChild(d);
  });
  updateTotal();
}
function addWallet(){ wallets.push({address:"",percent:10}); render(); }
function updateTotal(){ const t = wallets.reduce((s,w)=>s+(parseFloat(w.percent)||0),0); document.getElementById('totalBox').innerText = `Total Distribution: ${t}%`; }

async function saveAll(){
  const pwd = document.getElementById('savePwd').value;
  const res = await fetch('/api/admin/wallets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pwd,wallets})});
  const data = await res.json();
  document.getElementById('saveResult').innerHTML = `<pre style="background:#000;padding:10px">${JSON.stringify(data,null,2)}</pre>`;
  if(data.status) alert('✅ Saved! Total '+data.total+'%');
  else alert('❌ '+data.error);
}

async function test(){
  const amt = parseFloat(document.getElementById('testAmount').value)||100;
  const res = await fetch('/api/distribute',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({amount:amt})});
  const data = await res.json();
  document.getElementById('testResult').innerText = JSON.stringify(data,null,2);
}
</script>
</body>
</html>
    """
    return HTMLResponse(html)