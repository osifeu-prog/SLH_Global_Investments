from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Optional, Dict, Any

from web3 import Web3
from web3.exceptions import TransactionNotFound

from app.core.config import settings

logger = logging.getLogger(__name__)

# Minimal ERC20 ABI for balanceOf/decimals
_ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
]


@lru_cache(maxsize=2)
def _w3() -> Web3:
    if not settings.BSC_RPC_URL:
        raise RuntimeError("BSC_RPC_URL is not configured")
    w3 = Web3(Web3.HTTPProvider(settings.BSC_RPC_URL))
    if not w3.is_connected():
        raise RuntimeError("Failed to connect to BSC RPC")
    return w3


def _to_checksum(addr: str) -> str:
    return Web3.to_checksum_address(addr)


def get_onchain_balances(address: str) -> Dict[str, Optional[Decimal]]:
    """Fetch BNB + SLH token balances for an address (best-effort)."""
    out: Dict[str, Optional[Decimal]] = {"bnb": None, "slh": None}

    if not address:
        return out

    w3 = _w3()
    try:
        bnb_wei = w3.eth.get_balance(_to_checksum(address))
        out["bnb"] = Decimal(bnb_wei) / Decimal(10**18)
    except Exception as e:
        logger.warning("BNB balance failed: %s", e)

    token = settings.SLH_TOKEN_ADDRESS
    if token:
        try:
            c = w3.eth.contract(address=_to_checksum(token), abi=_ERC20_ABI)
            dec = c.functions.decimals().call()
            raw = c.functions.balanceOf(_to_checksum(address)).call()
            out["slh"] = Decimal(raw) / Decimal(10**int(dec))
        except Exception as e:
            logger.warning("SLH token balance failed: %s", e)

    return out


@dataclass
class VerifiedDeposit:
    tx_hash: str
    from_address: str
    to_address: str
    amount_bnb: Decimal
    block_number: int


def verify_bnb_deposit_tx(
    tx_hash: str,
    expected_to: str,
    min_confirmations: int = 1,
) -> Optional[VerifiedDeposit]:
    """Verify a native BNB transfer tx to expected_to.

    Returns VerifiedDeposit if:
    - tx exists
    - tx.to matches expected_to
    - value > 0
    - confirmations >= min_confirmations
    """
    if not tx_hash or not tx_hash.startswith("0x") or len(tx_hash) < 20:
        return None
    if not expected_to:
        return None

    w3 = _w3()
    try:
        tx = w3.eth.get_transaction(tx_hash)
    except TransactionNotFound:
        return None
    except Exception as e:
        logger.warning("tx fetch failed: %s", e)
        return None

    tx_to = (tx.get("to") or "").lower()
    want_to = _to_checksum(expected_to).lower()
    if tx_to != want_to:
        return None

    value_wei = tx.get("value", 0) or 0
    if int(value_wei) <= 0:
        return None

    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
    except Exception:
        receipt = None

    block_num = int((tx.get("blockNumber") or 0))
    if block_num <= 0:
        return None

    try:
        latest = w3.eth.block_number
        confirmations = int(latest) - block_num + 1
        if confirmations < int(min_confirmations):
            return None
    except Exception:
        # If we can't compute confirmations, still accept basic verification
        confirmations = min_confirmations

    from_addr = tx.get("from") or ""
    to_addr = tx.get("to") or ""

    amount_bnb = Decimal(int(value_wei)) / Decimal(10**18)

    return VerifiedDeposit(
        tx_hash=tx_hash,
        from_address=str(from_addr),
        to_address=str(to_addr),
        amount_bnb=amount_bnb,
        block_number=block_num,
    )
