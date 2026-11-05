from fastapi import FastAPI, Header, HTTPException, Depends
from sqlalchemy.orm import Session
from .validator import validate_transaction
from .idempotency import get_idempotent_response, save_idempotent_response, make_content_hash
from .profiles import get_profile_by_iban
from .database import get_db
from .models import Transaction
import os, uuid

app = FastAPI(title="FNF-CU Receiver API - Protocol 101.8")

@app.post("/api/v1/cash_transfer/request")
@app.post("/api/fiat-received")
async def fiat_received(payload: dict, x_api_key: str = Header(None), db: Session = Depends(get_db)):
    if x_api_key != os.getenv("API_SECRET_KEY"):
        raise HTTPException(status_code=401, detail="Invalid API key")

    idem_key = payload.get("idempotency_key")
    if not idem_key:
        raise HTTPException(status_code=400, detail="idempotency_key required - Sec 9")

    content_hash = make_content_hash(payload)

    try:
        existing = get_idempotent_response(idem_key, content_hash, db)
        if existing:
            return existing
    except Exception as e:
        if "IDEMPOTENCY_CONFLICT" in str(e):
            raise HTTPException(status_code=409, detail="IDEMPOTENCY_CONFLICT: Same key, different payload - generate new key")

    ok, msg = validate_transaction(payload)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    protocol = payload.get("payload", {}).get("receiver_specific", {}).get("protocol") or payload.get("protocol")
    if protocol != "101.8":
        raise HTTPException(status_code=400, detail="Expected protocol 101.8")

    sender_iban = payload.get("sender_iban") or payload.get("payload", {}).get("sender_iban")
    profile = get_profile_by_iban(sender_iban, db)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Sender IBAN {sender_iban} not whitelisted")

    receiver_ref = f"FNF-RECV-{uuid.uuid4().hex[:8].upper()}"
    
    resp = {
        "status": "success",
        "acknowledged": True,
        "receiver_reference": receiver_ref,
        "idempotency_key": idem_key,
        "settlement_status": "pending_bank_confirmation"
    }

    save_idempotent_response(idem_key, content_hash, resp, db)
    
    # Save main tx for settlement worker
    fiat_amount = payload.get("fiat_amount") or payload.get("amounts", {}).get("amount")
    registered_wallets = payload.get("payload", {}).get("receiver_specific", {}).get("registered_wallets") or [payload.get("payout_address")]
    
    db.add(Transaction(
        idempotency_key=idem_key,
        receiver_reference=receiver_ref,
        sender_iban=sender_iban,
        fiat_amount=fiat_amount,
        fiat_currency=payload.get("fiat_currency") or payload.get("amounts", {}).get("currency"),
        status="pending_bank_confirmation",
        banker_approved=False,
        registered_wallets=registered_wallets,
        raw_payload=payload
    ))
    db.commit()

    return resp

@app.post("/api/banker-approve/{receiver_reference}")
async def banker_approve(receiver_reference: str, x_api_key: str = Header(None), db: Session = Depends(get_db)):
    if x_api_key != os.getenv("API_SECRET_KEY"):
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    tx = db.query(Transaction).filter_by(receiver_reference=receiver_reference).first()
    if not tx:
        raise HTTPException(404, "Reference not found")
    
    # YOU manually verify MT103 credit via MT950/bank portal FIRST, then call this
    tx.banker_approved = True
    tx.status = "bank_confirmed_ready_for_usdt"
    db.commit()
    
    # Next: settlement worker picks this and triggers Factory 0x...
    return {"status": "bank_confirmed", "receiver_reference": receiver_reference, "next": "Settlement worker will auto-credit USDT to registered_wallets"}