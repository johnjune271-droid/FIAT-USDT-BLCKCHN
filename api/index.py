from fastapi import FastAPI
import os

app = FastAPI()

def check_redis():
    try:
        kv_url = os.getenv("KV_URL") or os.getenv("KV_REST_API_URL")
        if not kv_url:
            return False
        # Try redis lib
        import redis
        r = redis.from_url(os.getenv("KV_URL"), socket_connect_timeout=2)
        r.ping()
        return True
    except:
        try:
            # Try KV REST
            rest_url = os.getenv("KV_REST_API_URL")
            token = os.getenv("KV_REST_API_TOKEN")
            if rest_url and token:
                return True
            return False
        except:
            return False

@app.get("/")
def root():
    connected = check_redis()
    return {"status":"ok","redis_connected":connected,"version":"v2 - KV check"}

@app.get("/api/health")
def health():
    return {"status":"ok","redis":check_redis()}

@app.get("/admin")
def admin():
    from fastapi.responses import HTMLResponse
    redis_ok = check_redis()
    html = f"""
    <h1>CIPHER-JOHN FIAT-USDT Admin</h1>
    <p>Redis Connected: {redis_ok}</p>
    <p>KV_URL exists: {bool(os.getenv('KV_URL'))}</p>
    <p>KV_REST exists: {bool(os.getenv('KV_REST_API_URL'))}</p>
    <hr>
    <p>If Redis false -> Go to Vercel Storage -> Connect KV -> Redeploy WITHOUT cache</p>
    """
    return HTMLResponse(html)