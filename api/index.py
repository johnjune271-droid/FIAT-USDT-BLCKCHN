from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import os, json, time, base64

app = FastAPI(title="CIPHER-JOHN FIAT-USDT-BLCKCHN")

ADMIN_ID = os.getenv("ADMIN_ID", "cipherjohn")
ADMIN_PASS = os.getenv("ADMIN_PASS", "127366")

def get_kv():
    try:
        import redis
        r = redis.from_url(os.getenv("KV_URL"), decode_responses=True, socket_connect_timeout=3)
        r.ping()
        return r
    except:
        return None

def kv_get(key):
    kv = get_kv()
    if kv:
        try:
            v = kv.get(key)
            return json.loads(v) if v else None
        except:
            return None
    return None

def kv_set(key, value):
    kv = get_kv()
    if kv:
        try:
            kv.set(key, json.dumps(value))
            return True
        except:
            return False
    return False

def check_auth(request: Request):
    """Check Basic Auth or body auth"""
    # Check header
    auth = request.headers.get("authorization", "")
    if auth.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth[6:]).decode()
            user, pwd = decoded.split(":", 1)
            if user == ADMIN_ID and pwd == ADMIN_PASS:
                return True
        except:
            pass
    
    # Check query params (for simple UI)
    if request.query_params.get("id") == ADMIN_ID and request.query_params.get("pass") == ADMIN_PASS:
        return True
    
    return False

@app.get("/")
def root():
    kv = get_kv()
    wallets = kv_get("cipher:wallets") or []
    return {
        "status": "ok",
        "chain": "FIAT-USDT-BLCKCHN",
        "version": "v8 AUTH PROTECTED",
        "redis": bool(kv),
        "wallets": len(wallets),
        "admin": "/admin (Id: cipherjohn / Pass: 127366)"
    }

@app.get("/api/health")
def health():
    return {"redis": bool(get_kv()), "auth_id": ADMIN_ID, "wallets": len(kv_get("cipher:wallets") or [])}

@app.get("/api/wallets")
def get_wallets_api():
    wallets = kv_get("cipher:wallets") or []
    return {"wallets": wallets, "total_percent": sum(w.get("percent",0) for w in wallets)}

@app.post("/api/wallets")
async def save_wallets_api(request: Request):
    body = await request.json()
    
    # Auth check - allow either body auth or header
    auth_id = body.get("auth_id") or body.get("id")
    auth_pass = body.get("auth_pass") or body.get("pass") or body.get("password")
    
    # Also check header
    if not (auth_id == ADMIN_ID and auth_pass == ADMIN_PASS):
        if not check_auth(request):
            return JSONResponse({"error": "Unauthorized. Need Id: cipherjohn Pass: 127366"}, status_code=401)
    
    wallets = body.get("wallets", [])
    cleaned = []
    for w in wallets:
        addr = str(w.get("address","")).strip()
        if not addr:
            continue
        cleaned.append({"address": addr, "percent": float(w.get("percent",0)), "chain": "TRON" if addr.startswith("T") else "ETH"})
    
    total = sum(w["percent"] for w in cleaned)
    if total > 100:
        return JSONResponse({"error": f"Total {total}% > 100%"}, status_code=400)
    
    kv_set("cipher:wallets", cleaned)
    return {"status": "saved", "wallets": cleaned, "total_percent": total}

@app.post("/api/distribute")
async def distribute_api(request: Request):
    body = await request.json()
    
    # Auth check
    auth_id = body.get("auth_id") or body.get("id")
    auth_pass = body.get("auth_pass") or body.get("pass")
    if not (auth_id == ADMIN_ID and auth_pass == ADMIN_PASS):
        if not check_auth(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    amount = float(body.get("amount", 0))
    wallets = kv_get("cipher:wallets") or []
    if not wallets:
        return JSONResponse({"error": "No wallets"}, status_code=400)
    
    payouts = [{"address": w["address"], "percent": w["percent"], "amount": amount * w["percent"]/100} for w in wallets]
    
    # Save tx history
    tx_record = {"id": f"dist_{int(time.time())}", "timestamp": time.time(), "input": amount, "payouts": payouts}
    history = kv_get("cipher:transactions") or []
    history.append(tx_record)
    kv_set("cipher:transactions", history[-50:])
    
    return {"status": "calculated", "input": amount, "total_percent": sum(w["percent"] for w in wallets), "payouts": payouts, "note": "Add PRIVATE_KEY + ALCHEMY_RPC for real USDT move"}

@app.get("/api/balance")
def balance_api(address: str = ""):
    if not address:
        return JSONResponse({"error": "address required"}, status_code=400)
    try:
        from ethers_provider import get_balance_eth, get_tron_balance
        result = get_tron_balance(address) if address.startswith("T") else get_balance_eth(address)
        return {"address": address, "balance": result}
    except Exception as e:
        return {"address": address, "balance": {"error": str(e)}}

@app.get("/api/transactions")
def tx_api(request: Request):
    if not check_auth(request):
        # Allow with query params ?id=cipherjohn&pass=127366
        if not (request.query_params.get("id") == ADMIN_ID and request.query_params.get("pass") == ADMIN_PASS):
            return JSONResponse({"error": "Unauthorized - use ?id=cipherjohn&pass=127366"}, status_code=401)
    txs = kv_get("cipher:transactions") or []
    return {"transactions": txs[::-1], "count": len(txs)}

@app.post("/api/admin/login")
async def login_api(request: Request):
    body = await request.json()
    uid = body.get("id") or body.get("auth_id")
    pwd = body.get("pass") or body.get("password") or body.get("auth_pass")
    if uid == ADMIN_ID and pwd == ADMIN_PASS:
        return {"status": "ok", "message": "Login successful"}
    return JSONResponse({"error": "Wrong Id or Pass"}, status_code=401)

@app.get("/admin")
def admin_ui():
    return HTMLResponse(f"""
<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>CIPHER ADMIN - AUTH</title>
<style>
body{{background:#000;color:#0f0;font-family:monospace;padding:15px}}
.card{{border:2px solid #0f0;padding:20px;margin:15px 0;border-radius:10px;background:#0a0a0a}}
input{{background:#000;color:#0f0;border:1px solid #0f0;padding:12px;width:100%;margin:5px 0;border-radius:5px}}
.row{{display:flex;gap:10px;margin:8px 0}}
.row input:first-child{{flex:1}}.row input:nth-child(2){{width:90px}}
button{{background:#0f0;color:#000;border:none;padding:12px 20px;font-weight:bold;cursor:pointer;border-radius:5px;margin:5px}}
.btn-red{{background:#ff2040;color:#fff}}
#total{{font-size:24px;color:yellow;text-align:center;padding:15px;border:2px solid yellow;margin:15px 0;border-radius:8px}}
pre{{background:#000;padding:15px;border:1px solid #333;overflow:auto}}
.hidden{{display:none}}
.login-box{{max-width:400px;margin:100px auto;text-align:center;border:2px solid #0f0;padding:30px;border-radius:15px;background:#111}}
</style></head>
<body>

<div id="loginPage" class="login-box">
<h1>🔐 CIPHER-JOHN ADMIN</h1>
<p>Enter Admin Credentials</p>
<input type="text" id="loginId" placeholder="Id (cipherjohn)" value="cipherjohn">
<input type="password" id="loginPass" placeholder="Pass (127366)" value="">
<button onclick="doLogin()" style="width:100%;margin-top:15px;font-size:18px">LOGIN</button>
<p id="loginError" style="color:red"></p>
<p style="font-size:12px;color:#666;margin-top:20px">Default: cipherjohn / 127366<br>Set ADMIN_ID / ADMIN_PASS in Vercel to change</p>
</div>

<div id="mainPage" class="hidden">
<h1>🔐 CIPHER-JOHN FIAT-USDT-BLCKCHN</h1>
<p>Logged in as: <span id="loggedUser" style="color:yellow"></span> <button onclick="logout()" class="btn-red">Logout</button></p>

<div class="card">
<h2>💼 Wallet Distribution</h2>
<div id="walletList"></div>
<button onclick="addWallet()">+ Add Wallet</button>
<div id="totalBox">Total: 0%</div>
<button onclick="saveWallets()" style="width:100%;font-size:18px">💾 SAVE TO BLOCKCHAIN</button>
<pre id="saveMsg"></pre>
</div>

<div class="card">
<h2>🧪 Test Distribution</h2>
<div class="row"><input type="number" id="testAmt" value="100"><button onclick="testDist()">Calculate</button></div>
<pre id="testOut"></pre>
</div>

<div class="card">
<h2>📊 Data</h2>
<a href="/api/wallets?id=cipherjohn&pass=127366" target="_blank" style="color:#0f0">View Wallets</a> | 
<a href="/api/transactions?id=cipherjohn&pass=127366" target="_blank" style="color:#0f0">Transactions</a> | 
<a href="/" target="_blank" style="color:#0f0">Root</a>
</div>
</div>

<script>
let wallets = [];
let authId = localStorage.getItem('cipher_id') || 'cipherjohn';
let authPass = localStorage.getItem('cipher_pass') || '';

function checkLoggedIn(){{
  if(authId && authPass){{
    document.getElementById('loginId').value = authId;
    document.getElementById('loginPass').value = authPass;
    // Auto login if saved
    if(localStorage.getItem('cipher_logged')==='1'){{ doLogin(true); }}
  }}
}}

async function doLogin(silent=false){{
  const id = document.getElementById('loginId').value;
  const pass = document.getElementById('loginPass').value;
  if(!id || !pass){{ document.getElementById('loginError').innerText='Enter Id and Pass'; return; }}
  
  try{{
    const res = await fetch('/api/admin/login', {{
      method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{id, pass}})
    }});
    const data = await res.json();
    if(res.ok){{
      authId = id; authPass = pass;
      localStorage.setItem('cipher_id', id);
      localStorage.setItem('cipher_pass', pass);
      localStorage.setItem('cipher_logged','1');
      document.getElementById('loginPage').classList.add('hidden');
      document.getElementById('mainPage').classList.remove('hidden');
      document.getElementById('loggedUser').innerText = id;
      loadWallets();
    }} else {{
      if(!silent) document.getElementById('loginError').innerText = data.error || 'Login failed';
    }}
  }}catch(e){{
    document.getElementById('loginError').innerText = 'Error: '+e.message;
  }}
}}

function logout(){{
  localStorage.removeItem('cipher_logged');
  location.reload();
}}

async function loadWallets(){{
  const r = await fetch('/api/wallets');
  const j = await r.json();
  wallets = j.wallets && j.wallets.length>0 ? j.wallets : [{{address:"",percent:10}},{{address:"",percent:10}},{{address:"",percent:10}},{{address:"",percent:10}},{{address:"",percent:10}}];
  render();
}}
function render(){{
  const c = document.getElementById('walletList');
  c.innerHTML='';
  wallets.forEach((w,i)=>{{
    const div=document.createElement('div'); div.className='row';
    div.innerHTML=`<input value="${{w.address||''}}" placeholder="0x or T address" oninput="wallets[${{i}}].address=this.value"><input type="number" value="${{w.percent||0}}" oninput="wallets[${{i}}].percent=parseFloat(this.value)||0;updateTotal()"><button class="btn-red" onclick="wallets.splice(${{i}},1);render()">X</button>`;
    c.appendChild(div);
  }});
  updateTotal();
}}
function addWallet(){{ wallets.push({{address:"",percent:10}}); render(); }}
function updateTotal(){{ document.getElementById('totalBox').innerText='Total: '+wallets.reduce((s,w)=>s+(parseFloat(w.percent)||0),0)+'%'; }}
async function saveWallets(){{
  document.getElementById('saveMsg').innerText='Saving...';
  const res = await fetch('/api/wallets', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{id:authId, pass:authPass, wallets}})}});
  const data = await res.json();
  document.getElementById('saveMsg').innerText=JSON.stringify(data,null,2);
  if(data.status==='saved') alert('✅ SAVED '+data.total_percent+'%');
  else alert('❌ '+data.error);
}}
async function testDist(){{
  const amt = parseFloat(document.getElementById('testAmt').value)||100;
  const res = await fetch('/api/distribute', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{id:authId, pass:authPass, amount:amt}})}});
  document.getElementById('testOut').innerText=JSON.stringify(await res.json(),null,2);
}}
checkLoggedIn();
</script>
</body>
</html>
    """)

# Also add to requirements.txt: fastapi, redis, web3==6.15.0, tronpy==0.6.0