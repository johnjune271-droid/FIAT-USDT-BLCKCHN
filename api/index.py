from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import os, uuid, json, secrets
from datetime import datetime

# Alchemy + Tron
from ethers_provider import distribute_erc20, distribute_trc20, is_trc_wallet

app = FastAPI(title="CIPHER-JOHN CONSOLE v3 - 50% Auto Distributor")
security = HTTPBasic()
ADMIN_USER = "cipher-john"
ADMIN_PASS = "127365"

def check_auth(credentials: HTTPBasicCredentials = Depends(security)):
    if not (secrets.compare_digest(credentials.username, ADMIN_USER) and secrets.compare_digest(credentials.password, ADMIN_PASS)):
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})
    return credentials.username

redis_client = None
try:
    import redis
    kv_url = os.getenv("KV_URL") or os.getenv("REDIS_URL")
    if kv_url:
        redis_client = redis.from_url(kv_url, decode_responses=True, socket_timeout=5)
        redis_client.ping()
except Exception as e:
    print(f"Redis fail {e}")
    redis_client = None

MEM_LOG = []

def redis_get_list():
    if not redis_client:
        return MEM_LOG
    try:
        items = redis_client.lrange("request_log", 0, 199)
        return [json.loads(x) for x in items]
    except:
        return MEM_LOG

def redis_push(entry):
    if not redis_client:
        MEM_LOG.append(entry)
        return
    try:
        redis_client.lpush("request_log", json.dumps(entry))
        redis_client.ltrim("request_log", 0, 199)
    except:
        MEM_LOG.append(entry)

def redis_update_status(receiver_ref, new_status, distributions=None, tx_results=None):
    # Update in Redis or Memory
    target_list = MEM_LOG if not redis_client else None
    if not redis_client:
        for e in MEM_LOG:
            if e["receiver_reference"] == receiver_ref:
                e["status"] = new_status
                e["approved_at"] = datetime.utcnow().isoformat()
                e["approved_by"] = "CIPHER-JOHN"
                if distributions: e["distributions"] = distributions
                if tx_results: e["tx_results"] = tx_results
        return True
    try:
        items = redis_client.lrange("request_log", 0, 199)
        redis_client.delete("request_log")
        for item_str in reversed(items):
            entry = json.loads(item_str)
            if entry["receiver_reference"] == receiver_ref:
                entry["status"] = new_status
                entry["approved_at"] = datetime.utcnow().isoformat()
                entry["approved_by"] = "CIPHER-JOHN"
                if distributions: entry["distributions"] = distributions
                if tx_results: entry["tx_results"] = tx_results
            redis_client.rpush("request_log", json.dumps(entry))
        redis_client.ltrim("request_log", -200, -1)
        return True
    except Exception as e:
        print(f"Update error {e}")
        return False

def redis_set_distributions(receiver_ref, distributions):
    # Validate: max 5, sum 50
    if len(distributions) > 5:
        raise Exception("Max 5 wallets allowed")
    total = sum([d.get("percent",0) for d in distributions])
    if abs(total - 50) > 0.01:
        raise Exception(f"Total percent must be exactly 50, got {total}")
    # Save
    if not redis_client:
        for e in MEM_LOG:
            if e["receiver_reference"] == receiver_ref:
                e["distributions"] = distributions
                e["total_percent"] = total
        return True
    try:
        items = redis_client.lrange("request_log", 0, 199)
        redis_client.delete("request_log")
        for item_str in reversed(items):
            entry = json.loads(item_str)
            if entry["receiver_reference"] == receiver_ref:
                entry["distributions"] = distributions
                entry["total_percent"] = total
            redis_client.rpush("request_log", json.dumps(entry))
        redis_client.ltrim("request_log", -200, -1)
        return True
    except Exception as e:
        print(f"Set dist error {e}")
        return False

@app.get("/")
def root():
    ok = False
    try:
        if redis_client:
            redis_client.ping()
            ok = True
    except:
        pass
    return {"status":"ok","console":"CIPHER-JOHN v3 - 50% Auto Distributor","admin":"/admin","receiver":"/api/v1/cash_transfer/request","redis_connected": ok}

@app.post("/api/v1/cash_transfer/request")
@app.post("/api/fiat-received")
async def fiat_received(payload: dict):
    idem_key = payload.get("idempotency_key", f"no-key-{uuid.uuid4().hex[:4]}")
    receiver_ref = f"FNF-RECV-{uuid.uuid4().hex[:8].upper()}"
    resp = {"status":"success","acknowledged":True,"receiver_reference":receiver_ref,"idempotency_key":idem_key,"settlement_status":"pending_bank_confirmation","timestamp": datetime.utcnow().isoformat()}
    # Support both old registered_wallets and new distributions
    wallets_old = payload.get("payload",{}).get("receiver_specific",{}).get("registered_wallets",[])
    dist_new = payload.get("payload",{}).get("receiver_specific",{}).get("distributions",[])
    log_entry = {
        "time": datetime.utcnow().isoformat(),
        "receiver_reference": receiver_ref,
        "idempotency_key": idem_key,
        "sender_iban": payload.get("sender_iban",""),
        "fiat_amount": payload.get("fiat_amount",0),
        "fiat_currency": payload.get("fiat_currency","USD"),
        "wallets": wallets_old,
        "distributions": dist_new, # New field
        "total_percent": sum([d.get("percent",0) for d in dist_new]) if dist_new else 0,
        "protocol": payload.get("protocol","101.8"),
        "full_payload": payload,
        "status":"pending_bank_confirmation"
    }
    redis_push(log_entry)
    return resp

@app.get("/api/admin/recent-requests")
def recent_requests(user: str = Depends(check_auth)):
    logs = redis_get_list()
    return {"hits": logs[::-1], "total": len(logs), "redis": bool(redis_client)}

# NEW: Set distributions from Admin Panel
@app.post("/api/admin/set-distributions/{receiver_ref}")
def set_distributions(receiver_ref: str, body: dict, user: str = Depends(check_auth)):
    distributions = body.get("distributions", [])
    try:
        ok = redis_set_distributions(receiver_ref, distributions)
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to update")
        return {"status":"saved","receiver_reference":receiver_ref,"distributions":distributions,"total": sum([d.get("percent",0) for d in distributions])}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# UPDATED: Banker Approve now AUTO DISTRIBUTES 50%
@app.post("/api/banker-approve/{receiver_ref}")
def banker_approve(receiver_ref: str, user: str = Depends(check_auth)):
    # Get current entry
    logs = redis_get_list()
    entry = None
    for e in logs:
        if e["receiver_reference"] == receiver_ref:
            entry = e
            break
    if not entry:
        raise HTTPException(status_code=404, detail="Reference not found")
    
    distributions = entry.get("distributions", [])
    if not distributions:
        raise HTTPException(status_code=400, detail="No distributions set. Add 5 wallets with total 50% from admin panel first.")
    
    # Validate 50%
    total = sum([d.get("percent",0) for d in distributions])
    if abs(total - 50) > 0.01:
        raise HTTPException(status_code=400, detail=f"Total percent must be 50, got {total}")

    fiat_amount = float(entry.get("fiat_amount",0))
    
    # Auto distribute via Alchemy/TronGrid
    tx_results = []
    try:
        # Check if TRC20
        is_trc = any([is_trc_wallet(d["wallet"]) for d in distributions])
        if is_trc:
            tx_results = distribute_trc20(fiat_amount, distributions)
        else:
            tx_results = distribute_erc20(fiat_amount, distributions, receiver_ref)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Distribution failed: {str(e)}")

    ok = redis_update_status(receiver_ref, "bank_confirmed_usdt_triggered", distributions, tx_results)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update Redis")
    
    return {
        "status":"approved_and_distributed",
        "receiver_reference":receiver_ref,
        "new_status":"bank_confirmed_usdt_triggered",
        "total_received": fiat_amount,
        "total_distributed": fiat_amount * 0.5,
        "distributions": tx_results,
        "approved_by":"CIPHER-JOHN",
        "approved_at": datetime.utcnow().isoformat()
    }

@app.get("/admin", response_class=HTMLResponse)
def admin_panel(user: str = Depends(check_auth)):
    return """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>CIPHER-JOHN CONSOLE v3</title><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-[#050505] text-white min-h-screen"><div class="max-w-7xl mx-auto p-4">
<div class="flex justify-between items-center py-6 border-b border-gray-800"><div><h1 class="text-2xl font-black tracking-widest">CIPHER-JOHN CONSOLE v3</h1><p class="text-xs text-green-400 tracking-[0.3em]">101.8 // 50% AUTO DISTRIBUTOR // 5 WALLETS MAX</p></div><div class="flex gap-2"><span class="text-xs bg-green-900 text-green-300 px-3 py-1 rounded-full">AUTH: cipher-john</span><button onclick="loadData()" class="bg-white text-black px-4 py-2 rounded text-sm font-bold">Refresh</button></div></div>
<div class="grid grid-cols-3 gap-4 my-6"><div class="bg-[#111] p-4 rounded border border-gray-800"><p class="text-gray-400 text-xs">Total</p><p id="total" class="text-2xl font-bold">0</p></div><div class="bg-[#111] p-4 rounded border border-gray-800"><p class="text-gray-400 text-xs">Pending</p><p id="pending" class="text-2xl font-bold text-yellow-400">0</p></div><div class="bg-[#111] p-4 rounded border border-gray-800"><p class="text-gray-400 text-xs">Redis</p><p id="redis" class="text-sm font-bold">-</p></div></div>
<div id="list" class="space-y-4"></div></div>
<script>
async function loadData(){
  try{
    const res = await fetch('/api/admin/recent-requests', {credentials: 'include'});
    const j = await res.json();
    const data = j.hits || [];
    document.getElementById('total').innerText = j.total;
    document.getElementById('pending').innerText = data.filter(d=>d.status.includes('pending')).length;
    document.getElementById('redis').innerText = j.redis ? 'CONNECTED' : 'MEMORY';
    if(data.length===0){document.getElementById('list').innerHTML='<p class="text-gray-600 text-center py-20">No hits</p>';return}
    document.getElementById('list').innerHTML = data.map((h,i)=>`
<div class="bg-[#111] border ${h.status.includes('triggered')?'border-green-800':'border-gray-800'} rounded p-4">
<div class="flex justify-between gap-4">
<div class="flex-1 min-w-0">
<p class="font-mono font-bold ${h.status.includes('triggered')?'text-green-400':'text-yellow-400'}">${h.receiver_reference} <span class="text-[10px] bg-[#222] px-2 py-1 rounded ml-2">${h.status}</span> <span class="text-[10px] bg-blue-900 px-2 py-1 rounded ml-2">${h.fiat_amount} ${h.fiat_currency}</span></p>
<p class="text-sm mt-2">${h.sender_iban} | ${h.time}</p>
${h.approved_at ? `<p class="text-xs text-green-400">APPROVED: ${h.approved_at} | Distributed: ${h.tx_results ? JSON.stringify(h.tx_results.map(t=>t.amount+'->'+t.wallet.substring(0,10))) : ''}</p>` : ''}
<div class="mt-3 bg-black p-3 rounded border border-gray-800">
<p class="text-xs text-gray-400 mb-2 font-bold">DISTRIBUTIONS (Max 5, Sum must be 50%) - Total: ${h.total_percent || 0}%</p>
<div id="dist-${i}">${(h.distributions||[]).map((d,idx)=>`<div class="flex gap-2 text-xs mb-1"><span class="flex-1 font-mono bg-[#222] p-1 rounded">${d.wallet}</span><span class="bg-blue-900 px-2 py-1 rounded">${d.percent}%</span><span class="bg-gray-800 px-2 py-1 rounded">${(h.fiat_amount * d.percent /100).toFixed(2)} USDT</span></div>`).join('') || '<p class="text-xs text-gray-600">No distributions set - add below</p>'}</div>
${h.tx_results ? `<div class="mt-2 text-[11px] text-green-400">Tx Hashes: ${h.tx_results.map(r=>`<div class="font-mono break-all">${r.wallet.substring(0,15)}... -> ${r.txHash}</div>`).join('')}</div>` : ''}
</div>
</div>
<div class="flex flex-col gap-2 shrink-0 w-64">
<button onclick="viewPayload(${i})" class="text-xs border border-gray-600 px-3 py-2 rounded">View JSON</button>
<div class="bg-[#1a1a1a] p-2 rounded border border-gray-700">
<p class="text-[10px] text-gray-400 mb-1">ADD WALLET + %</p>
<input id="wallet-${i}" placeholder="TQn9... or 0x..." class="w-full text-xs bg-black border border-gray-700 rounded p-1 mb-1 font-mono">
<input id="percent-${i}" type="number" placeholder="Percent (e.g. 20)" class="w-full text-xs bg-black border border-gray-700 rounded p-1 mb-1">
<button onclick="addWallet(${i}, '${h.receiver_reference}')" class="w-full text-xs bg-blue-600 hover:bg-blue-500 px-2 py-1 rounded">+ Add Wallet</button>
<button onclick="saveDist('${h.receiver_reference}', ${i})" class="w-full text-xs bg-yellow-600 hover:bg-yellow-500 px-2 py-1 rounded mt-1">Save Distributions</button>
</div>
${h.status.includes('pending') ? `<button onclick="approve('${h.receiver_reference}')" class="text-xs bg-green-600 hover:bg-green-500 px-3 py-2 rounded font-bold animate-pulse">APPROVE & AUTO-DISTRIBUTE 50%</button>` : `<span class="text-xs bg-green-900 text-green-300 px-3 py-2 rounded text-center">✓ DISTRIBUTED 50%</span>`}
</div>
</div>
<pre id="payload-${i}" class="hidden mt-3 bg-black p-3 text-[11px] overflow-auto rounded border border-gray-800">${JSON.stringify(h.full_payload, null, 2)}</pre>
</div>`).join('');
    window._data = data;
  }catch(e){document.getElementById('list').innerHTML='<p class="text-red-400">Error: '+e+'</p>'}
}
function viewPayload(i){document.getElementById('payload-'+i).classList.toggle('hidden')}
async function addWallet(idx, ref){
  const walletInput = document.getElementById('wallet-'+idx);
  const percentInput = document.getElementById('percent-'+idx);
  const wallet = walletInput.value.trim();
  const percent = parseFloat(percentInput.value);
  if(!wallet || !percent){ alert('Enter wallet and percent'); return; }
  if(!window._data[idx].distributions) window._data[idx].distributions = [];
  if(window._data[idx].distributions.length >=5){ alert('Max 5 wallets'); return; }
  window._data[idx].distributions.push({wallet, percent});
  walletInput.value=''; percentInput.value='';
  // Re-render locally
  const div = document.getElementById('dist-'+idx);
  div.innerHTML = window._data[idx].distributions.map(d=>`<div class="flex gap-2 text-xs mb-1"><span class="flex-1 font-mono bg-[#222] p-1 rounded">${d.wallet}</span><span class="bg-blue-900 px-2 py-1 rounded">${d.percent}%</span></div>`).join('');
}
async function saveDist(ref, idx){
  const dist = window._data[idx].distributions || [];
  const total = dist.reduce((s,d)=>s+d.percent,0);
  if(total !==50){ alert('Total must be exactly 50%, current '+total+'%'); return; }
  if(dist.length>5){ alert('Max 5'); return; }
  try{
    const res = await fetch('/api/admin/set-distributions/'+ref, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({distributions: dist}), credentials:'include'});
    const j = await res.json();
    if(res.ok){ alert('Saved: '+total+'%'); loadData(); } else{ alert('Failed: '+JSON.stringify(j)) }
  }catch(e){ alert('Error: '+e) }
}
async function approve(ref){
  if(!confirm('CONFIRM REAL BANK CREDIT for '+ref+'?\\nThis will AUTO-DISTRIBUTE 50% via Alchemy/TronGrid to wallets set in admin panel.')) return;
  try{
    const res = await fetch('/api/banker-approve/'+ref, {method:'POST', credentials: 'include'});
    const j = await res.json();
    if(res.ok){ alert('APPROVED & DISTRIBUTED 50%: '+JSON.stringify(j.distributions)); loadData(); }
    else{ alert('Failed: '+JSON.stringify(j)) }
  }catch(e){ alert('Error: '+e) }
}
loadData(); setInterval(loadData, 5000)
</script></body></html>"""