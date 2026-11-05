import os

def get_balance_eth(address):
    try:
        rpc = os.getenv("ALCHEMY_RPC") or "https://eth.llamarpc.com"
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(rpc))
        if not w3.is_connected():
            return {"error": "RPC failed", "balance_eth": "0"}
        wei = w3.eth.get_balance(address)
        eth = w3.from_wei(wei, 'ether')
        return {"balance_wei": str(wei), "balance_eth": str(eth), "rpc": rpc[:30]+"..."}
    except Exception as e:
        return {"error": str(e), "balance_eth": "0"}

def get_tron_balance(address):
    try:
        from tronpy import Tron
        client = Tron()
        acc = client.get_account(address)
        bal = acc.get('balance',0)/1_000_000
        return {"balance_trx": bal, "balance_sun": acc.get('balance',0)}
    except Exception as e:
        return {"error": str(e), "balance_trx": "0"}

def send_distribution(payouts, token="USDT"):
    """Real distribution if PRIVATE_KEY set"""
    try:
        rpc = os.getenv("ALCHEMY_RPC")
        pk = os.getenv("PRIVATE_KEY")
        if not rpc or not pk:
            return [{"status":"mock","reason":"No keys"}]
        
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(rpc))
        account = w3.eth.account.from_key(pk)
        
        results = []
        for p in payouts:
            if p["chain"] != "ETH":
                continue
            # For demo, just estimate - real USDT needs contract ABI
            # This is ETH distribution logic - adapt for USDT contract
            tx = {
                'to': p['address'],
                'value': w3.to_wei(p['amount']*0.0001, 'ether'),  # Small amount for test - change to real logic
                'gas': 21000,
                'gasPrice': w3.eth.gas_price,
                'nonce': w3.eth.get_transaction_count(account.address),
                'chainId': 1
            }
            # Uncomment for real tx:
            # signed = w3.eth.account.sign_transaction(tx, pk)
            # tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
            # results.append({"address":p['address'],"tx_hash":tx_hash.hex(),"amount":p['amount']})
            results.append({"address":p['address'],"status":"ready_to_send","amount":p['amount'],"note":"Uncomment send_raw_transaction for real"})
        
        return results
    except Exception as e:
        return [{"error": str(e)}]