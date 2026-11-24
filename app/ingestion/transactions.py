"""Idempotent Transaction Ingestion Pipeline with SHA-256 Deduplication."""
import hashlib
import csv
import io
from datetime import datetime, date
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from app.db.models import Transaction, Category, Account

def generate_txn_hash(user_id: int, txn_date: str, amount: float, merchant: str, description: str) -> str:
    raw = f"{user_id}:{txn_date}:{amount:.2f}:{merchant.strip().lower()}:{description.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def ingest_transactions_csv(
    db: Session, 
    csv_content: str, 
    user_id: int = 1
) -> Dict[str, Any]:
    """
    Ingests transactions from CSV content idempotently.
    Expected CSV columns: txn_date, amount, direction, category, merchant, description
    """
    reader = csv.DictReader(io.StringIO(csv_content))
    processed = 0
    inserted = 0
    duplicates = 0

    # Cache categories and default account
    cats = {c.name.lower(): c.category_id for c in db.query(Category).all()}
    account = db.query(Account).filter_by(user_id=user_id).first()
    acc_id = account.account_id if account else 1

    txns_to_add = []
    seen_hashes = set()

    for row in reader:
        processed += 1
        d_str = row.get("txn_date", "").strip()
        amt_str = row.get("amount", "0").strip()
        direction = row.get("direction", "debit").strip().lower()
        cat_name = row.get("category", "other").strip().lower()
        merchant = row.get("merchant", "").strip()
        description = row.get("description", "").strip()

        try:
            amt = float(amt_str)
            t_date = datetime.strptime(d_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        h = generate_txn_hash(user_id, d_str, amt, merchant, description)

        # Check existing in current batch or database
        if h in seen_hashes:
            duplicates += 1
            continue

        exists = db.query(Transaction.txn_id).filter_by(source_hash=h).first()
        if exists:
            duplicates += 1
            continue

        seen_hashes.add(h)

        cat_id = cats.get(cat_name)

        txns_to_add.append(Transaction(
            user_id=user_id,
            account_id=acc_id,
            txn_date=t_date,
            amount=amt,
            direction=direction,
            category_id=cat_id,
            merchant=merchant,
            description=description,
            source_hash=h
        ))
        inserted += 1

    if txns_to_add:
        db.bulk_save_objects(txns_to_add)
        db.commit()

    return {
        "rows_processed": processed,
        "rows_inserted": inserted,
        "duplicates_skipped": duplicates
    }
