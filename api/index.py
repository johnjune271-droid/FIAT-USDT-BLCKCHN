from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import os
import json

app = FastAPI()

KV_PREFIX = "cipher:"

def get_kv():
    try:
        kv_url = os.getenv("KV_URL")
        if kv_url:
            import redis
            r = redis.from_url(kv_url, decode_responses=True, socket_connect_timeout=3)
            r.ping()
            return r
    except Exception as e:
        print(f"KV error: {e}")
    return None

def get_wallets():
    kv = get_kv()
    if kv:
        data = kv.get(f"{KV_PREFIX}wallets")
        if data:
            try:
                return json.loads(data)
            except:
                pass
    # Default 5 wallets - 50% distribution
    return [
        {"address": os.getenv("WALLET_1", ""), "percent": 10},
        {"address": os.getenv("WALLET_2", ""), "percent": 10},
        {"address": os.getenv("WALLET_3", ""), "percent": 10},
        {"address": os.getenv("WALLET_4", ""), "percent": 10},
        {"address": os.getenv("WALLET_5", ""), "percent": 10},
    ]

@app.get("/")
def root():
    kv = get_kv()
    return {
        "status": "ok",
        "redis_connected": bool(kv),
        "version": "CIPHER-JOHN v3 - FULL",
        "wallets_configured": len([w for w in get_wallets() if w.get("address")])
    }

@app.get("/api/health")
def health():
    kv = get_kv()
    return {"status": "ok", "redis": bool(kv), "kv_url_exists": bool(os.getenv("KV_URL"))}

@app.get("/api/balance")
def balance(address: str = ""):
    try:
        # Safe import inside function
        from api.ethers_provider import get_balance_eth
        bal = get_balance_eth(address) if address else {"error": "address required"}
        return {"address": address, "balance": bal}
    except Exception as e:
        return {"error": str(e), "balance": "0", "mock": True}

@app.post("/api/distribute")
async def distribute(request: Request):
    try:
        body = await request.json()
        amount = float(body.get("amount", 0))
        wallets = get_wallets()
        # 50% distribution logic
        distribution_amount = amount * 0.5
        results = []
        for w in wallets:
            if w.get("address"):
                share = distribution_amount * (w["percent"] / 50.0)  # 50% total
                results.append({"address": w["address"], "share": share})
        
        kv = get_kv()
        if kv:
            kv.set(f"{KV_PREFIX}last_distribution", json.dumps({"amount": amount, "results": results}))
        
        return {"status": "distributed", "total": amount, "distributed_50_percent": distribution_amount, "results": results}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/admin")
def admin():
    wallets = get_wallets()
    kv = get_kv()
    env_check = {
        "KV_URL": bool(os.getenv("KV_URL")),
        "ALCHEMY_RPC": bool(os.getenv("ALCHEMY_RPC")),
        "PRIVATE_KEY": bool(os.getenv("PRIVATE_KEY")),
        "CONTRACT_ADDRESS": bool(os.getenv("CONTRACT_ADDRESS")),
        "TRONGRID": bool(os.getenv("TRONGRID_API_KEY")),
    }
    html = f"""
    <html><head><title>CIPHER-JOHN Admin</title></head>
    <body style="font-family:monospace;padding:20px;background:#0a0a0a;color:#0f0">
    <h1>CIPHER-JOHN FIAT-USDT-BLCKCHN</h1>
    <p>Redis: {bool(kv)} | Version: FULL v3</p>
    <h2>Env Check</h2><pre>{json.dumps(env_check, indent=2)}</pre>
    <h2>5 Wallets - 50% Distribution</h2><pre>{json.dumps(wallets, indent=2)}</pre>
    <h2>Test</h2>
    <p><a href="/">/</a> | <a href="/api/health">/api/health</a> | <a href="/api/balance?address=0x0000000000000000000000000000000000000000">/api/balance</a></p>
    <hr>
    <h3>Distribute Test (POST /api/distribute)</h3>
    <p>curl -X POST https://fiat-usdt-block-c9ki288yf-john-a362.vercel.app/api/distribute -H "Content-Type: application/json" -d '{{"amount": 100}}'</p>
    </body></html>
    """
    return HTMLResponse(html)