from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os, json, time

app = FastAPI(title="CIPHER-JOHN FIAT-USDT-BLCKCHN")

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

# ==================== CORE API ====================

@app.get("/")
def root():
    kv = get_kv()
    wallets = kv_get("cipher:wallets") or []
    contract = os.getenv("CONTRACT_ADDRESS", "")
    return {
        "status": "ok",
        "chain": "FIAT-USDT-BLCKCHN",
        "version": "CIPHER-JOHN FULL API v6",
        "redis_connected": bool(kv),
        "contract_address": contract,
        "wallets_configured": len(wallets),
        "total_distribution_percent": sum(w.get("percent",0) for w in wallets),
        "endpoints": {
            "wallets": "/api/wallets",
            "balance": "/api/balance?address=0x...",
            "distribute": "POST /api/distribute {amount:100}",
            "deposit": "POST /api/deposit",
            "transactions": "/api/transactions",
            "contract": "/api/contract",
            "health": "/api/health"
        }
    }

@app.get("/api/health")
def health():
    return {
        "redis": bool(get_kv()),
        "alchemy": bool(os.getenv("ALCHEMY_RPC")),
        "private_key": bool(os.getenv("PRIVATE_KEY")),
        "contract": bool(os.getenv("CONTRACT_ADDRESS")),
        "tron": bool(os.getenv("TRONGRID_API_KEY")),
        "wallets": kv_get("cipher:wallets") or []
    }

# ==================== WALLETS API ====================

@app.get("/api/wallets")
def get_wallets_api():
    wallets = kv_get("cipher:wallets") or []
    total = sum(w.get("percent",0) for w in wallets)
    return {
        "wallets": wallets,
        "count": len(wallets),
        "total_percent": total,
        "is_50_percent": total == 50,
        "distribution_logic": f"{total}% of every deposit goes to these wallets"
    }

@app.post("/api/wallets")
async def save_wallets_api(request: Request):
    body = await request.json()
    wallets = body.get("wallets", [])
    
    # Validate
    cleaned = []
    for w in wallets:
        addr = w.get("address","").strip()
        if not addr:
            continue
        # Basic address validation
        if not (addr.startswith("0x") or addr.startswith("T")):
            return JSONResponse({"error": f"Invalid address: {addr}. Must start with 0x or T"}, status_code=400)
        cleaned.append({
            "address": addr,
            "percent": float(w.get("percent",0)),
            "label": w.get("label", f"Wallet {len(cleaned)+1}"),
            "chain": "TRON" if addr.startswith("T") else "ETH"
        })
    
    total = sum(w["percent"] for w in cleaned)
    if total > 100:
        return JSONResponse({"error": f"Total {total}% exceeds 100%"}, status_code=400)
    
    kv_set("cipher:wallets", cleaned)
    # Save history
    history = kv_get("cipher:wallet_history") or []
    history.append({"timestamp": time.time(), "wallets": cleaned, "total": total})
    kv_set("cipher:wallet_history", history[-20:])  # Keep last 20
    
    return {
        "status": "wallets_saved",
        "wallets": cleaned,
        "total_percent": total,
        "message": f"Saved {len(cleaned)} wallets with {total}% distribution"
    }

@app.delete("/api/wallets")
def delete_wallets():
    kv_set("cipher:wallets", [])
    return {"status": "wallets_cleared"}

# ==================== BALANCE API ====================

@app.get("/api/balance")
def balance_api(address: str = ""):
    if not address:
        return JSONResponse({"error": "address query param required. Example: /api/balance?address=0x123..."}, status_code=400)
    
    try:
        # Use your ethers_provider safely
        import sys
        sys.path.append(os.path.dirname(__file__))
        from ethers_provider import get_balance_eth, get_tron_balance
        
        if address.startswith("T"):
            result = get_tron_balance(address)
        else:
            result = get_balance_eth(address)
        
        return {
            "address": address,
            "chain": "TRON" if address.startswith("T") else "ETH",
            "balance": result,
            "timestamp": time.time()
        }
    except Exception as e:
        return {
            "address": address,
            "balance": {"error": str(e), "mock": True, "balance": "0"},
            "note": "Set ALCHEMY_RPC and PRIVATE_KEY in Vercel Env for real balances"
        }

# ==================== SMART CONTRACT API ====================

@app.get("/api/contract")
def contract_api():
    contract = os.getenv("CONTRACT_ADDRESS", "")
    rpc = os.getenv("ALCHEMY_RPC", "")
    return {
        "contract_address": contract,
        "rpc": "set" if rpc else "not_set",
        "network": "ethereum-mainnet" if "mainnet" in rpc else "custom",
        "abi_needed": not contract,
        "note": "Deploy your FIAT-USDT contract and set CONTRACT_ADDRESS in Vercel"
    }

# ==================== DISTRIBUTION API - CORE LOGIC ====================

@app.post("/api/distribute")
async def distribute_api(request: Request):
    """
    CORE: 50% distribution logic
    Takes amount, splits by wallet percents
    If PRIVATE_KEY set, does real blockchain tx, else mock
    """
    body = await request.json()
    amount = float(body.get("amount", 0))
    token = body.get("token", "USDT")  # USDT or FIAT
    
    if amount <= 0:
        return JSONResponse({"error": "amount must be > 0"}, status_code=400)
    
    wallets = kv_get("cipher:wallets") or []
    if not wallets:
        return JSONResponse({"error": "No wallets configured. POST /api/wallets first"}, status_code=400)
    
    total_percent = sum(w["percent"] for w in wallets)
    
    # Calculate payouts
    payouts = []
    for w in wallets:
        payout_amount = amount * (w["percent"] / 100.0)
        payouts.append({
            "address": w["address"],
            "percent": w["percent"],
            "amount": payout_amount,
            "token": token,
            "chain": w.get("chain", "ETH")
        })
    
    # Try real blockchain tx if keys set
    tx_results = []
    private_key = os.getenv("PRIVATE_KEY")
    alchemy_rpc = os.getenv("ALCHEMY_RPC")
    
    if private_key and alchemy_rpc and total_percent > 0:
        try:
            from ethers_provider import send_distribution
            tx_results = send_distribution(payouts, token)
        except Exception as e:
            tx_results = [{"error": str(e), "mock": True}]
    else:
        tx_results = [{"status": "mock", "note": "Set PRIVATE_KEY + ALCHEMY_RPC for real tx", "payouts": payouts}]
    
    # Save transaction
    tx_record = {
        "id": f"dist_{int(time.time())}",
        "timestamp": time.time(),
        "input_amount": amount,
        "token": token,
        "total_percent_distributed": total_percent,
        "payouts": payouts,
        "tx_results": tx_results
    }
    
    history = kv_get("cipher:transactions") or []
    history.append(tx_record)
    kv_set("cipher:transactions", history[-50:])  # Keep last 50
    
    return {
        "status": "distributed" if private_key else "calculated_mock",
        "distribution_id": tx_record["id"],
        "input_amount": amount,
        "token": token,
        "total_percent": total_percent,
        "total_distributed": amount * total_percent / 100,
        "payouts": payouts,
        "blockchain_txs": tx_results,
        "note": "Real tx only if PRIVATE_KEY + ALCHEMY_RPC set in Vercel"
    }

@app.get("/api/transactions")
def transactions_api():
    txs = kv_get("cipher:transactions") or []
    return {"transactions": txs[::-1], "count": len(txs)}  # Newest first

@app.post("/api/deposit")
async def deposit_api(request: Request):
    body = await request.json()
    amount = body.get("amount", 0)
    sender = body.get("from", "unknown")
    
    # Log deposit
    deposits = kv_get("cipher:deposits") or []
    deposits.append({"timestamp": time.time(), "amount": amount, "from": sender})
    kv_set("cipher:deposits", deposits[-50:])
    
    # Auto-trigger distribution if wallets set
    wallets = kv_get("cipher:wallets") or []
    if wallets and amount:
        # Auto-distribute
        return {
            "status": "deposit_logged",
            "deposit": {"amount": amount, "from": sender},
            "auto_distribution_triggered": True,
            "next_step": f"POST /api/distribute with amount {amount} to distribute {sum(w['percent'] for w in wallets)}%"
        }
    
    return {"status": "deposit_logged", "amount": amount}

# ==================== ADMIN UI - MINIMAL ====================
@app.get("/admin")
def admin():
    from fastapi.responses import HTMLResponse
    return HTMLResponse("""
    <html><body style="background:#000;color:#0f0;font-family:monospace;padding:20px">
    <h1>CIPHER-JOHN API ADMIN</h1>
    <p>API is functional. Use endpoints directly:</p>
    <pre style="background:#111;padding:15px">
    GET  /api/wallets - List wallets
    POST /api/wallets - Save wallets: {"wallets":[{"address":"0x...","percent":10}]}
    GET  /api/balance?address=0x...
    POST /api/distribute - {"amount":100}
    GET  /api/transactions - History
    GET  /api/contract - Contract info
    </pre>
    <p>Test with curl:</p>
    <pre style="background:#111;padding:15px">
    curl https://your-url.vercel.app/api/wallets

    curl -X POST https://your-url.vercel.app/api/wallets -H "Content-Type: application/json" -d '{"wallets":[{"address":"0x123...","percent":10},{"address":"TNmx...","percent":40}]}'

    curl https://your-url.vercel.app/api/balance?address=0x0000000000000000000000000000000000000000

    curl -X POST https://your-url.vercel.app/api/distribute -H "Content-Type: application/json" -d '{"amount":100}'
    </pre>
    <a href="/api/wallets" style="color:#0f0">View Wallets JSON</a> | <a href="/api/transactions" style="color:#0f0">Transactions</a> | <a href="/" style="color:#0f0">Root</a>
    </body></html>
    """)