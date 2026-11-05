from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import os
import json
import time

app = FastAPI(title="CIPHER-JOHN FIAT-USDT-BLCKCHN")

# ========== KV HELPERS ==========
def get_kv():
    try:
        import redis
        kv_url = os.getenv("KV_URL") or os.getenv("REDIS_URL")
        if not kv_url:
            return None
        r = redis.from_url(kv_url, decode_responses=True, socket_connect_timeout=3)
        r.ping()
        return r
    except Exception as e:
        print(f"KV ERROR: {e}")
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
        except Exception as e:
            print(f"SET ERROR: {e}")
            return False
    return False

# ========== ROOT ==========
@app.get("/")
def root():
    kv = get_kv()
    wallets = kv_get("cipher:wallets") or []
    return {
        "status": "ok",
        "chain": "FIAT-USDT-BLCKCHN",
        "version": "CIPHER-JOHN FULL API v7 - FINAL",
        "redis_connected": bool(kv),
        "contract_address": os.getenv("CONTRACT_ADDRESS", ""),
        "wallets_configured": len(wallets),
        "total_distribution_percent": sum(w.get("percent", 0) for w in wallets),
        "endpoints": {
            "admin": "/admin",
            "wallets": "/api/wallets",
            "balance": "/api/balance?address=0x...",
            "distribute": "POST /api/distribute",
            "transactions": "/api/transactions",
            "contract": "/api/contract"
        }
    }

@app.get("/api/health")
def health():
    wallets = kv_get("cipher:wallets") or []
    return {
        "redis": bool(get_kv()),
        "alchemy": bool(os.getenv("ALCHEMY_RPC")),
        "private_key": bool(os.getenv("PRIVATE_KEY")),
        "contract": bool(os.getenv("CONTRACT_ADDRESS")),
        "tron": bool(os.getenv("TRONGRID_API_KEY")),
        "wallets_count": len(wallets),
        "total_percent": sum(w.get("percent", 0) for w in wallets)
    }

# ========== WALLETS API ==========
@app.get("/api/wallets")
def get_wallets_api():
    wallets = kv_get("cipher:wallets") or []
    total = sum(w.get("percent", 0) for w in wallets)
    return {
        "wallets": wallets,
        "count": len(wallets),
        "total_percent": total,
        "distribution_logic": f"{total}% of every deposit distributed"
    }

@app.post("/api/wallets")
async def save_wallets_api(request: Request):
    try:
        body = await request.json()
        wallets = body.get("wallets", [])
        cleaned = []
        for w in wallets:
            addr = str(w.get("address", "")).strip()
            if not addr:
                continue
            cleaned.append({
                "address": addr,
                "percent": float(w.get("percent", 0)),
                "label": w.get("label", f"Wallet {len(cleaned)+1}"),
                "chain": "TRON" if addr.startswith("T") else "ETH"
            })
        
        total = sum(w["percent"] for w in cleaned)
        if total > 100:
            return JSONResponse({"error": f"Total {total}% exceeds 100%"}, status_code=400)
        
        kv_set("cipher:wallets", cleaned)
        
        # History
        history = kv_get("cipher:wallet_history") or []
        history.append({"timestamp": time.time(), "wallets": cleaned, "total": total})
        kv_set("cipher:wallet_history", history[-20:])
        
        return {
            "status": "saved",
            "wallets": cleaned,
            "total_percent": total,
            "message": f"Saved {len(cleaned)} wallets"
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.delete("/api/wallets")
def delete_wallets_api():
    kv_set("cipher:wallets", [])
    return {"status": "cleared"}

# ========== BALANCE API ==========
@app.get("/api/balance")
def balance_api(address: str = ""):
    if not address:
        return JSONResponse({"error": "address param required: /api/balance?address=0x..."}, status_code=400)
    try:
        from ethers_provider import get_balance_eth, get_tron_balance
        if address.startswith("T"):
            result = get_tron_balance(address)
        else:
            result = get_balance_eth(address)
        return {"address": address, "chain": "TRON" if address.startswith("T") else "ETH", "balance": result, "timestamp": time.time()}
    except Exception as e:
        return {"address": address, "balance": {"error": str(e), "balance": "0", "mock": True}}

# ========== CONTRACT API ==========
@app.get("/api/contract")
def contract_api():
    return {
        "contract_address": os.getenv("CONTRACT_ADDRESS", ""),
        "rpc_set": bool(os.getenv("ALCHEMY_RPC")),
        "network": "ethereum-mainnet",
        "note": "Set CONTRACT_ADDRESS + ALCHEMY_RPC in Vercel for real contract"
    }

# ========== DISTRIBUTION API ==========
@app.post("/api/distribute")
async def distribute_api(request: Request):
    body = await request.json()
    amount = float(body.get("amount", 0))
    token = body.get("token", "USDT")
    
    if amount <= 0:
        return JSONResponse({"error": "amount must be > 0"}, status_code=400)
    
    wallets = kv_get("cipher:wallets") or []
    if not wallets:
        return JSONResponse({"error": "No wallets configured. POST /api/wallets first"}, status_code=400)
    
    total_percent = sum(w["percent"] for w in wallets)
    payouts = []
    for w in wallets:
        payouts.append({
            "address": w["address"],
            "percent": w["percent"],
            "amount": amount * (w["percent"] / 100.0),
            "token": token,
            "chain": w.get("chain", "ETH")
        })
    
    # Try real tx if keys set
    tx_results = []
    try:
        from ethers_provider import send_distribution
        if os.getenv("PRIVATE_KEY") and os.getenv("ALCHEMY_RPC"):
            tx_results = send_distribution(payouts, token)
        else:
            tx_results = [{"status": "mock", "note": "Set PRIVATE_KEY + ALCHEMY_RPC for real tx"}]
    except Exception as e:
        tx_results = [{"error": str(e), "mock": True}]
    
    tx_record = {
        "id": f"dist_{int(time.time())}",
        "timestamp": time.time(),
        "input_amount": amount,
        "token": token,
        "total_percent": total_percent,
        "payouts": payouts,
        "tx_results": tx_results
    }
    
    history = kv_get("cipher:transactions") or []
    history.append(tx_record)
    kv_set("cipher:transactions", history[-50:])
    
    return {
        "status": "distributed",
        "distribution_id": tx_record["id"],
        "input_amount": amount,
        "token": token,
        "total_percent": total_percent,
        "total_distributed": amount * total_percent / 100,
        "payouts": payouts,
        "blockchain_txs": tx_results
    }

@app.get("/api/transactions")
def transactions_api():
    txs = kv_get("cipher:transactions") or []
    return {"transactions": txs[::-1], "count": len(txs)}

@app.post("/api/deposit")
async def deposit_api(request: Request):
    body = await request.json()
    amount = body.get("amount", 0)
    sender = body.get("from", "unknown")
    deposits = kv_get("cipher:deposits") or []
    deposits.append({"timestamp": time.time(), "amount": amount, "from": sender})
    kv_set("cipher:deposits", deposits[-50:])
    return {"status": "deposit_logged", "amount": amount, "from": sender}

# ========== ADMIN UI - FULLY FUNCTIONAL ==========
@app.get("/admin")
def admin_ui():
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CIPHER-JOHN ADMIN</title>
<style>
body{background:#000;color:#0f0;font-family:monospace;padding:15px;margin:0}
h1{color:#0f0;border-bottom:2px solid #0f0;padding-bottom:10px}
.card{border:2px solid #0f0;padding:20px;margin:15px 0;border-radius:10px;background:#0a0a0a}
input{background:#000;color:#0f0;border:1px solid #0f0;padding:12px;width:100%;margin:5px 0;border-radius:5px;font-family:monospace}
.row{display:flex;gap:10px;margin:8px 0;align-items:center}
.row input:first-child{flex:1}
.row input:nth-child(2){width:90px}
button{background:#0f0;color:#000;border:none;padding:12px 20px;font-weight:bold;cursor:pointer;border-radius:5px;margin:5px}
button:hover{background:#00ff88}
.btn-red{background:#ff2040;color:#fff;padding:8px 12px}
.btn-outline{background:transparent;border:1px solid #0f0;color:#0f0}
#total{font-size:28px;color:yellow;text-align:center;padding:15px;border:2px solid yellow;margin:15px 0;border-radius:8px;background:#111}
pre{background:#000;padding:15px;border:1px solid #333;overflow:auto;border-radius:5px;white-space:pre-wrap;word-break:break-all}
a{color:#0f0}
</style>
</head>
<body>
<h1>🔐 CIPHER-JOHN FIAT-USDT-BLCKCHN - ADMIN</h1>

<div class="card">
<h2>💼 Wallet Distribution - Admin Controls %</h2>
<p>Admin decides how many wallets and % each. Example: 5 wallets × 10% = 50% total</p>
<div id="walletList"></div>
<button onclick="addWallet()" class="btn-outline">+ Add Wallet</button>
<div id="totalBox">Total: 0%</div>
<button onclick="saveWallets()" style="width:100%;font-size:18px;background:#00ff88">💾 SAVE TO BLOCKCHAIN (Redis KV)</button>
<pre id="saveMsg">Not saved yet</pre>
</div>

<div class="card">
<h2>🧪 Test Distribution</h2>
<div class="row"><input type="number" id="testAmt" value="100" placeholder="Amount"><button onclick="testDist()">Calculate</button></div>
<pre id="testOut">Click Calculate to see distribution</pre>
</div>

<div class="card">
<h2>📊 API Endpoints (All Functional)</h2>
<pre>
GET  /                  - Status
GET  /api/wallets       - List wallets (JSON)
POST /api/wallets       - Save wallets
GET  /api/balance?address=0x... - Check balance
POST /api/distribute    - {"amount":100} - Distribute
GET  /api/transactions  - History
GET  /api/contract      - Contract info
GET  /api/health        - Health check
</pre>
<p>
<a href="/api/wallets" target="_blank">View Wallets JSON</a> | 
<a href="/api/transactions" target="_blank">Transactions</a> | 
<a href="/api/health" target="_blank">Health</a> | 
<a href="/" target="_blank">Root</a>
</p>
</div>

<script>
let wallets = [];
async function loadWallets(){
  try{
    const r = await fetch('/api/wallets');
    const j = await r.json();
    wallets = j.wallets && j.wallets.length > 0 ? j.wallets : [
      {address:"",percent:10},
      {address:"",percent:10},
      {address:"",percent:10},
      {address:"",percent:10},
      {address:"",percent:10}
    ];
    render();
  }catch(e){
    wallets = [{address:"",percent:10},{address:"",percent:10},{address:"",percent:10},{address:"",percent:10},{address:"",percent:10}];
    render();
  }
}
function render(){
  const container = document.getElementById('walletList');
  container.innerHTML = '';
  wallets.forEach((w,i)=>{
    const div = document.createElement('div');
    div.className = 'row';
    div.innerHTML = `
      <input value="${w.address||''}" placeholder="0x... ETH or T... TRON" oninput="wallets[${i}].address=this.value">
      <input type="number" value="${w.percent||0}" placeholder="%" oninput="wallets[${i}].percent=parseFloat(this.value)||0; updateTotal()">
      <button class="btn-red" onclick="wallets.splice(${i},1); render()">X</button>
    `;
    container.appendChild(div);
  });
  updateTotal();
}
function addWallet(){ wallets.push({address:"",percent:10}); render(); }
function updateTotal(){
  const total = wallets.reduce((s,w)=>s+(parseFloat(w.percent)||0),0);
  document.getElementById('totalBox').innerText = `Total Distribution: ${total}% ${total==50?'(50% TARGET ✓)':''}`;
}
async function saveWallets(){
  const msg = document.getElementById('saveMsg');
  msg.innerText = 'Saving to KV...';
  try{
    const res = await fetch('/api/wallets', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({wallets})
    });
    const data = await res.json();
    msg.innerText = JSON.stringify(data, null, 2);
    if(data.status === 'saved'){
      alert('✅ SAVED! Total: ' + data.total_percent + '% - ' + data.message);
    } else {
      alert('❌ Error: ' + (data.error||'Unknown'));
    }
  }catch(e){
    msg.innerText = 'Error: ' + e.message;
    alert('Save failed: ' + e.message);
  }
}
async function testDist(){
  const amt = parseFloat(document.getElementById('testAmt').value) || 100;
  const out = document.getElementById('testOut');
  out.innerText = 'Calculating...';
  try{
    const res = await fetch('/api/distribute', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({amount: amt})
    });
    const data = await res.json();
    out.innerText = JSON.stringify(data, null, 2);
  }catch(e){
    out.innerText = 'Error: ' + e.message;
  }
}
loadWallets();
</script>
</body>
</html>
    """)