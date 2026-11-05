import os, time
from web3 import Web3
from .database import SessionLocal
from .models import Transaction

w3 = Web3(Web3.HTTPProvider(os.getenv("ALCHEMY_ETH_URL")))
FACTORY_ADDRESS = os.getenv("OWNER_WALLET") # Replace with Factory contract address

def process_settlement():
    db = SessionLocal()
    while True:
        tx = db.query(Transaction).filter_by(status="bank_confirmed_ready_for_usdt", banker_approved=True).first()
        if tx:
            try:
                # Your Factory.distribute() call to auto-split to registered_wallets
                # tx_hash = factory.functions.distribute(tx.registered_wallets, int(tx.usdt_amount * 1e6)).transact()
                print(f"Distributing to {tx.registered_wallets}")
                tx.status = "SETTLED"
                # tx.settlement_tx = tx_hash
                db.commit()
            except Exception as e:
                print(f"Settlement failed {e}")
                tx.status = "FAILED"
                db.commit()
        time.sleep(10)

if __name__ == "__main__":
    process_settlement()