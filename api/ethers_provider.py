import os

# USDT ABI - only transfer function needed
USDT_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }
]

def get_balance_eth(address):
    try:
        rpc = os.getenv("ALCHEMY_RPC") or "https://eth.llamarpc.com"
        usdt_contract_addr = os.getenv("USDT_CONTRACT") or "0xdAC17F958D2ee523a2206206994597C13D831ec7"
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(rpc))
        if not w3.is_connected():
            return {"error": "RPC failed"}
        
        # Check ETH balance
        wei = w3.eth.get_balance(Web3.to_checksum_address(address))
        eth = w3.from_wei(wei, 'ether')
        
        # Check USDT balance
        usdt = w3.eth.contract(address=Web3.to_checksum_address(usdt_contract_addr), abi=USDT_ABI)
        usdt_balance = usdt.functions.balanceOf(Web3.to_checksum_address(address)).call()
        usdt_balance_readable = usdt_balance / 10**6  # USDT has 6 decimals
        
        return {
            "eth_wei": str(wei),
            "eth": str(eth),
            "usdt_raw": str(usdt_balance),
            "usdt": str(usdt_balance_readable),
            "contract": usdt_contract_addr
        }
    except Exception as e:
        return {"error": str(e), "mock": True}

def get_tron_balance(address):
    try:
        from tronpy import Tron
        client = Tron()
        acc = client.get_account(address)
        # For TRON USDT (TRC20) - contract TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t
        return {"trx": acc.get('balance',0)/1_000_000, "note": "TRON USDT needs TRC20 contract call"}
    except Exception as e:
        return {"error": str(e)}

def send_distribution(payouts, token="USDT"):
    """
    REAL USDT TRANSFER - This actually moves USDT
    payouts = [{"address": "0x...", "amount": 10}, ...]
    """
    rpc = os.getenv("ALCHEMY_RPC")
    pk = os.getenv("PRIVATE_KEY")
    usdt_contract_addr = os.getenv("USDT_CONTRACT") or "0xdAC17F958D2ee523a2206206994597C13D831ec7"
    
    if not rpc or not pk:
        return [{"status": "error", "reason": "Set PRIVATE_KEY + ALCHEMY_RPC in Vercel Env Vars"}]
    
    try:
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(rpc))
        account = w3.eth.account.from_key(pk)
        sender = account.address
        
        print(f"Sending from: {sender}")
        
        usdt_contract = w3.eth.contract(
            address=Web3.to_checksum_address(usdt_contract_addr),
            abi=USDT_ABI
        )
        
        results = []
        for p in payouts:
            try:
                to_addr = p["address"]
                amount = float(p["amount"])
                
                # Skip TRON addresses for ETH USDT
                if to_addr.startswith("T"):
                    results.append({"address": to_addr, "status": "skip", "reason": "TRON address - need separate TRON distribution"})
                    continue
                
                # USDT has 6 decimals: 10 USDT = 10 * 10^6
                amount_raw = int(amount * 10**6)
                
                # Check sender USDT balance
                balance = usdt_contract.functions.balanceOf(Web3.to_checksum_address(sender)).call()
                if balance < amount_raw:
                    results.append({"address": to_addr, "status": "failed", "reason": f"Insufficient USDT. Have {balance/10**6}, need {amount}"})
                    continue
                
                # Build transaction
                nonce = w3.eth.get_transaction_count(sender)
                tx = usdt_contract.functions.transfer(
                    Web3.to_checksum_address(to_addr),
                    amount_raw
                ).build_transaction({
                    'from': sender,
                    'gas': 100000,  # USDT transfer needs ~65k
                    'gasPrice': w3.eth.gas_price,
                    'nonce': nonce,
                    'chainId': 1  # Mainnet, use 11155111 for Sepolia testnet
                })
                
                # Sign and send
                signed = w3.eth.account.sign_transaction(tx, pk)
                tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
                
                results.append({
                    "address": to_addr,
                    "status": "sent",
                    "amount": amount,
                    "amount_raw": str(amount_raw),
                    "tx_hash": tx_hash.hex(),
                    "explorer": f"https://etherscan.io/tx/{tx_hash.hex()}",
                    "from": sender
                })
                
                # Small delay to avoid nonce collision
                import time
                time.sleep(1)
                
            except Exception as e:
                results.append({"address": p.get("address"), "status": "error", "error": str(e)})
        
        return results
        
    except Exception as e:
        return [{"status": "fatal_error", "error": str(e)}]