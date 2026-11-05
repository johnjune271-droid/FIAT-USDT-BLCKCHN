from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def root():
    return {"status":"ok","redis_connected":False,"version":"emergency fix - working"}

@app.get("/api/health")
def health():
    return {"status":"ok"}

@app.get("/admin")
def admin():
    from fastapi.responses import HTMLResponse
    return HTMLResponse("<h1>Admin - Site UP</h1><p>Now add Redis</p>")