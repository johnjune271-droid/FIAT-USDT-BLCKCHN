def validate_transaction(payload: dict):
    # Support both flat and nested formats
    fiat_amount = payload.get("fiat_amount") or payload.get("amounts", {}).get("amount", 0)
    try:
        fiat_amount = float(fiat_amount)
    except:
        return False, "Invalid amount"
    
    if fiat_amount <= 0:
        return False, "Invalid amount"
    if fiat_amount > 1000000:
        return False, "Amount exceeds limit - contact banker"

    sender_iban = payload.get("sender_iban") or payload.get("payload", {}).get("sender_iban") or payload.get("parties", {}).get("sender", {}).get("iban")
    if not sender_iban:
        return False, "sender_iban required"

    fiat_currency = payload.get("fiat_currency") or payload.get("amounts", {}).get("currency")
    if fiat_currency not in ["USD", "EUR"]:
        return False, "Only USD/EUR allowed"
    
    return True, "ok"