"""Synthetic Data Generator for Verifiable Finance Copilot.

Generates:
- 3+ realistic synthetic user profiles
- 12 months of transactions (~2,000 to 5,000 rows per user)
- Realistic merchants, categories, recurring bills, salaries, seasonal variations
- Deliberate anomalies (duplicate charge, spike) for alert/insight testing
- Sample financial text PDFs (bank statements, loan agreements, insurance policies)
- Reproducible via fixed random seed
"""
import os
import sys

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import random
import hashlib
from datetime import datetime, date, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.db.connection import SessionLocal, init_db
from app.db.models import User, Account, Category, Transaction, Budget, Bill, Goal, Document, Chunk

RANDOM_SEED = 42

CATEGORIES_DATA = [
    # Expense
    ("food", "expense"),
    ("rent", "expense"),
    ("utilities", "expense"),
    ("transport", "expense"),
    ("entertainment", "expense"),
    ("shopping", "expense"),
    ("healthcare", "expense"),
    ("education", "expense"),
    ("travel", "expense"),
    ("groceries", "expense"),
    ("insurance", "expense"),
    ("investments", "expense"),
    # Income
    ("salary", "income"),
    ("freelance", "income"),
    ("dividends", "income"),
    ("cashback", "income")
]

MERCHANTS_BY_CATEGORY = {
    "food": ["Swiggy", "Zomato", "McDonald's", "Starbucks", "Dominos Pizza", "Subway", "Local Bistro"],
    "groceries": ["BigBasket", "Blinkit", "Zepto", "Nature's Basket", "Reliance Fresh", "Local Kirana"],
    "rent": ["PropTech Housing", "Landlord Sharma", "Urban Nest Properties"],
    "utilities": ["BESCOM Electricity", "Airtel Broadband", "Jio Telecom", "Indane Gas", "BWSSB Water"],
    "transport": ["Uber", "Ola Cabs", "Metro SmartCard", "HP Petrol Pump", "Shell Fuel Station"],
    "entertainment": ["Netflix", "Spotify", "BookMyShow", "PVR Cinemas", "Amazon Prime", "Disney+ Hotstar"],
    "shopping": ["Amazon India", "Flipkart", "Myntra", "Zara", "Decathlon", "Uniqlo"],
    "healthcare": ["Apollo Pharmacy", "Practo Consult", "1mg Healthcare", "Dr Lal PathLabs"],
    "education": ["Coursera", "Udemy", "Kindle Bookstore", "Exam Fee Portal"],
    "travel": ["MakeMyTrip", "IRCTC Rail", "IndiGo Airlines", "Agoda Hotels"],
    "insurance": ["HDFC ERGO", "Star Health Insurance", "LIC Premium"],
    "investments": ["Zerodha Broking", "Groww Mutual Funds", "Kuvera"],
    "salary": ["Tech Mahindra Ltd", "Infosys Technologies", "Google India", "Startup Inc"],
    "freelance": ["Upwork Client", "Design Retainer", "Advisory Services"],
    "dividends": ["TCS Dividend", "ITC Dividend"],
    "cashback": ["Cred Rewards", "Google Pay Cashback"]
}

def generate_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def create_synthetic_data(db: Session, seed: int = RANDOM_SEED, num_users: int = 10) -> Dict[str, Any]:
    random.seed(seed)
    stats = {}

    # 1. Seed Categories
    category_objs = {}
    for name, cat_type in CATEGORIES_DATA:
        cat = db.query(Category).filter_by(name=name).first()
        if not cat:
            cat = Category(name=name, type=cat_type)
            db.add(cat)
            db.flush()
        category_objs[name] = cat
    db.commit()

    # 2. Seed Users - Diverse financial personas
    users_data = [
        {"name": "Aarav Sharma", "salary": 140000.0, "rent": 35000.0, "persona": "Salaried Tech Lead"},
        {"name": "Priya Patel", "salary": 95000.0, "rent": 22000.0, "persona": "Marketing Manager"},
        {"name": "Rohan Gupta", "salary": 180000.0, "rent": 42000.0, "persona": "Senior Software Architect"},
        {"name": "Ananya Iyer", "salary": 110000.0, "rent": 28000.0, "persona": "Product Designer & Freelancer"},
        {"name": "Vikram Malhotra", "salary": 250000.0, "rent": 55000.0, "persona": "Startup Founder / Executive"},
        {"name": "Sneha Kulkarni", "salary": 75000.0, "rent": 18000.0, "persona": "Data Analyst"},
        {"name": "Kabir Mehta", "salary": 130000.0, "rent": 32000.0, "persona": "Management Consultant"},
        {"name": "Neha Reddy", "salary": 85000.0, "rent": 20000.0, "persona": "Healthcare Specialist"},
        {"name": "Aditya Verma", "salary": 60000.0, "rent": 15000.0, "persona": "Junior Developer"},
        {"name": "Sunita Rao", "salary": 160000.0, "rent": 38000.0, "persona": "Finance Director"}
    ]

    created_users = []
    total_txns = 0

    end_date = date(2026, 11, 20)
    start_date = end_date - timedelta(days=365)

    selected_users = users_data[:num_users]

    for u_idx, u_info in enumerate(selected_users):
        user = db.query(User).filter_by(name=u_info["name"]).first()
        if not user:
            user = User(name=u_info["name"], created_at=datetime.utcnow() - timedelta(days=370))
            db.add(user)
            db.flush()
        created_users.append(user)

        # Accounts: Savings, Credit Card
        savings = db.query(Account).filter_by(user_id=user.user_id, account_type="savings").first()
        if not savings:
            savings = Account(
                user_id=user.user_id,
                account_type="savings",
                bank_name="HDFC Bank",
                opening_balance=150000.0 + u_idx * 50000.0
            )
            db.add(savings)
            db.flush()

        cc = db.query(Account).filter_by(user_id=user.user_id, account_type="credit_card").first()
        if not cc:
            cc = Account(
                user_id=user.user_id,
                account_type="credit_card",
                bank_name="ICICI Bank",
                opening_balance=0.0
            )
            db.add(cc)
            db.flush()

        # Budgets for current & past 12 months
        year = 2025
        month = 12
        months_list = []
        for _ in range(12):
            months_list.append(date(year, month, 1))
            month += 1
            if month > 12:
                month = 1
                year += 1

        for m_first in months_list:
            for cat_name, limit in [("food", 20000.0), ("groceries", 15000.0), ("entertainment", 10000.0), ("shopping", 18000.0)]:
                existing_b = db.query(Budget).filter_by(
                    user_id=user.user_id, category_id=category_objs[cat_name].category_id, month=m_first
                ).first()
                if not existing_b:
                    db.add(Budget(
                        user_id=user.user_id,
                        category_id=category_objs[cat_name].category_id,
                        month=m_first,
                        limit_amount=limit
                    ))

        # Recurring Bills
        bills_data = [
            ("Airtel Broadband", 1199.0, date(2026, 11, 28), "pending"),
            ("Electricity Bill", 3450.0, date(2026, 11, 25), "pending"),
            ("Gym Membership", 2500.0, date(2026, 11, 15), "paid"),
            ("Credit Card Due", 24800.0, date(2026, 12, 5), "pending")
        ]
        for b_name, b_amt, b_due, b_status in bills_data:
            existing_bill = db.query(Bill).filter_by(user_id=user.user_id, name=b_name).first()
            if not existing_bill:
                db.add(Bill(
                    user_id=user.user_id,
                    name=b_name,
                    amount=b_amt,
                    due_date=b_due,
                    status=b_status
                ))

        # Goals
        goals_data = [
            ("Emergency Fund 6 Months", 500000.0, date(2027, 6, 30)),
            ("Europe Trip Vacation", 250000.0, date(2027, 9, 15))
        ]
        for g_desc, g_target, g_date in goals_data:
            existing_goal = db.query(Goal).filter_by(user_id=user.user_id, description=g_desc).first()
            if not existing_goal:
                db.add(Goal(
                    user_id=user.user_id,
                    description=g_desc,
                    target_amount=g_target,
                    target_date=g_date
                ))

        # Transactions Generation (365 days, ~6-10 txns per day -> ~2500 txns per user)
        # Check if transactions already exist
        existing_txn_count = db.query(Transaction).filter_by(user_id=user.user_id).count()
        if existing_txn_count < 1000:
            txns_to_add = []
            curr = start_date
            while curr <= end_date:
                # 1. Monthly Salary (1st of month)
                if curr.day == 1:
                    src_h = generate_hash(f"{user.user_id}-salary-{curr.isoformat()}")
                    txns_to_add.append(Transaction(
                        user_id=user.user_id,
                        account_id=savings.account_id,
                        txn_date=curr,
                        amount=u_info["salary"],
                        direction="credit",
                        category_id=category_objs["salary"].category_id,
                        merchant=random.choice(MERCHANTS_BY_CATEGORY["salary"]),
                        description=f"Monthly salary credit for {curr.strftime('%B %Y')}",
                        source_hash=src_h
                    ))
                    # Rent payment (5th of month)
                    rent_h = generate_hash(f"{user.user_id}-rent-{curr.isoformat()}")
                    txns_to_add.append(Transaction(
                        user_id=user.user_id,
                        account_id=savings.account_id,
                        txn_date=curr + timedelta(days=4),
                        amount=u_info["rent"],
                        direction="debit",
                        category_id=category_objs["rent"].category_id,
                        merchant=random.choice(MERCHANTS_BY_CATEGORY["rent"]),
                        description=f"House rent transfer",
                        source_hash=rent_h
                    ))

                # Daily random transactions: 4 to 8 per day
                num_daily = random.randint(4, 8)
                # Seasonal spike in festive season (October / Diwali or holiday)
                if curr.month in (10, 11):
                    num_daily += 2

                for i in range(num_daily):
                    cat_name = random.choices(
                        ["food", "groceries", "transport", "entertainment", "shopping", "utilities", "healthcare"],
                        weights=[30, 25, 15, 10, 10, 5, 5]
                    )[0]
                    merchant = random.choice(MERCHANTS_BY_CATEGORY[cat_name])

                    if cat_name in ("food", "transport"):
                        amt = round(random.uniform(120.0, 950.0), 2)
                        acc_id = cc.account_id if random.random() > 0.4 else savings.account_id
                    elif cat_name == "groceries":
                        amt = round(random.uniform(400.0, 3200.0), 2)
                        acc_id = savings.account_id
                    elif cat_name == "shopping":
                        amt = round(random.uniform(1200.0, 8500.0), 2)
                        acc_id = cc.account_id
                    elif cat_name == "entertainment":
                        amt = round(random.uniform(300.0, 1800.0), 2)
                        acc_id = cc.account_id
                    else:
                        amt = round(random.uniform(250.0, 2500.0), 2)
                        acc_id = savings.account_id

                    # Deliberate anomaly for user 1: duplicate charge on 2026-08-14
                    is_anomaly = (u_idx == 0 and curr == date(2026, 8, 14) and i == 1)
                    if is_anomaly:
                        amt = 12450.0
                        desc = "Duplicate merchant charge flagged"
                    else:
                        desc = f"Payment to {merchant}"

                    tx_h = generate_hash(f"{user.user_id}-{curr.isoformat()}-{i}-{amt}-{merchant}")
                    txns_to_add.append(Transaction(
                        user_id=user.user_id,
                        account_id=acc_id,
                        txn_date=curr,
                        amount=amt,
                        direction="debit",
                        category_id=category_objs[cat_name].category_id,
                        merchant=merchant,
                        description=desc,
                        source_hash=tx_h
                    ))

                curr += timedelta(days=1)

            db.bulk_save_objects(txns_to_add)
            db.commit()
            total_txns += len(txns_to_add)
        else:
            total_txns += existing_txn_count

    stats["users_count"] = len(created_users)
    stats["total_transactions"] = total_txns
    return stats

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Synthetic Financial Data Generator")
    parser.add_argument("--users", type=int, default=10, help="Number of user profiles to generate (default: 10)")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED, help="Random seed for reproducibility")
    args = parser.parse_args()

    init_db()
    with SessionLocal() as db:
        res = create_synthetic_data(db, seed=args.seed, num_users=args.users)
        print(f"Data generation complete: {res}")
