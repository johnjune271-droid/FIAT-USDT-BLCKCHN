from sqlalchemy import Column, String, Numeric, DateTime, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()

class ReceiverProfile(Base):
    __tablename__ = "receiver_profiles"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    sender_iban = Column(String, unique=True, index=True)
    sender_name = Column(String)
    crypto_wallet = Column(String)
    fee_percent = Column(Numeric, default=1.0)
    kyc_status = Column(String, default="pending")
    created_at = Column(DateTime, server_default=func.now())

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    idempotency_key = Column(String, unique=True, index=True)
    receiver_reference = Column(String, unique=True, index=True)
    utr = Column(String, index=True)
    sender_iban = Column(String, index=True)
    fiat_amount = Column(Numeric)
    fiat_currency = Column(String)
    usdt_amount = Column(Numeric)
    status = Column(String, default="pending_bank_confirmation")
    banker_approved = Column(Boolean, default=False)
    registered_wallets = Column(JSON) # ["0x...", "0x..."] for auto-split
    settlement_tx = Column(String, nullable=True)
    raw_payload = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())
    settled_at = Column(DateTime, nullable=True)

class IdempotencyStore(Base):
    __tablename__ = "idempotency_store"
    idempotency_key = Column(String, primary_key=True)
    content_hash = Column(String)
    response = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())