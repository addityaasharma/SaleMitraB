from config.extension import db
from models.admin import VendorWallet, VendorWalletTransaction
from datetime import datetime


def get_or_create_wallet(vendor_id):
    wallet = VendorWallet.query.filter_by(vendor_id=vendor_id).first()
    if not wallet:
        wallet = VendorWallet(
            vendor_id=vendor_id, balance=0.0, total_earned=0.0, total_withdrawn=0.0
        )
        db.session.add(wallet)
        db.session.flush()
    return wallet


def credit_wallet(vendor_id, amount, source, reference_id=None, note=None):
    if amount <= 0:
        return None
    wallet = get_or_create_wallet(vendor_id)
    wallet.balance = round(wallet.balance + amount, 2)
    wallet.total_earned = round(wallet.total_earned + amount, 2)
    wallet.updated_at = datetime.utcnow()

    txn = VendorWalletTransaction(
        wallet_id=wallet.id,
        type="credit",
        source=source,
        amount=amount,
        balance_after=wallet.balance,
        reference_id=reference_id,
        note=note,
    )
    db.session.add(txn)
    return txn


def debit_wallet(vendor_id, amount, source, reference_id=None, note=None):
    if amount <= 0:
        return None
    wallet = get_or_create_wallet(vendor_id)
    if amount > wallet.balance:
        raise ValueError(
            f"Insufficient wallet balance. Available: {wallet.balance}, requested: {amount}"
        )

    wallet.balance = round(wallet.balance - amount, 2)
    if source == "payout_withdrawal":
        wallet.total_withdrawn = round(wallet.total_withdrawn + amount, 2)
    wallet.updated_at = datetime.utcnow()

    txn = VendorWalletTransaction(
        wallet_id=wallet.id,
        type="debit",
        source=source,
        amount=amount,
        balance_after=wallet.balance,
        reference_id=reference_id,
        note=note,
    )
    db.session.add(txn)
    return txn
