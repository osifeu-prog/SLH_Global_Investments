# app/blockchain.py
# On-chain SLH hook – prepared but NOT enabled.
# We keep it as a strict stub so nothing can accidentally send funds.

from __future__ import annotations

def send_slh_onchain(*, to_address: str, amount_slh, meta: dict | None = None):
    raise NotImplementedError("On-chain SLH transfer hook is prepared but NOT enabled.")
