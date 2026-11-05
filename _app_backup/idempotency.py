import hashlib, json
from sqlalchemy import text

def make_content_hash(payload: dict) -> str:
    copy = {k: v for k, v in payload.items() if k not in ["idempotency_key", "message_id", "timestamp"]}
    return hashlib.sha256(json.dumps(copy, sort_keys=True).encode()).hexdigest()

def get_idempotent_response(key, content_hash, db):
    row = db.execute(text("SELECT content_hash, response FROM idempotency_store WHERE idempotency_key=:k"), {"k": key}).fetchone()
    if not row: 
        return None
    if row[0] == content_hash:
        return row[1]
    else:
        raise Exception("IDEMPOTENCY_CONFLICT")

def save_idempotent_response(key, content_hash, response, db):
    db.execute(text("INSERT INTO idempotency_store (idempotency_key, content_hash, response) VALUES (:k,:h,:r) ON CONFLICT (idempotency_key) DO NOTHING"), 
               {"k": key, "h": content_hash, "r": json.dumps(response)})
    db.commit()