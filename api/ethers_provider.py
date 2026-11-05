import os

def get_balance_eth(address):
    try:
        rpc = os.getenv("ALCHEMY_RPC") or os.getenv("ETH_RPC") or "https://eth.llamarpc.com"
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(rpc))
        if not w3.is_connected():
            return {"error": "RPC not connected", "balance": "0"}
        bal_wei = w3.eth.get_balance(address)
        bal_eth = w3.from_wei(bal_wei, 'ether')
        return {"balance_eth": str(bal_eth), "balance_wei": str(bal_wei)}
    except Exception as e:
        return {"error": str(e), "balance": "0", "mock": True}

def get_tron_balance(address):
    try:
        from tronpy import Tron
        client = Tron(provider="https://api.trongrid.io")
        acc = client.get_account(address)
        balance = acc.get('balance', 0) / 1_000_000
        return {"balance_trx": balance}
    except Exception as e:
        return {"error": str(e), "balance": "0"}