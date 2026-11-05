from sqlalchemy import text

def get_profile_by_iban(iban: str, db):
    row = db.execute(text("SELECT * FROM receiver_profiles WHERE sender_iban=:iban AND kyc_status='approved'"), {"iban": iban}).fetchone()
    return row