"""One-Click Database Initializer & Seeder for Neon PostgreSQL."""
import os
import sys
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.db.models import Base
from scripts.generate_data import create_synthetic_data
from scripts.generate_sample_documents import generate_and_index_documents

def init_neon_database(database_url: str, num_users: int = 10):
    print(f"Connecting to remote PostgreSQL database...")
    # Ensure SSL mode is enabled for Neon
    if "sslmode" not in database_url and "neon.tech" in database_url:
        database_url += "?sslmode=require" if "?" not in database_url else "&sslmode=require"

    engine = create_engine(database_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)

    # 1. Enable pgvector extension if supported
    with engine.connect() as conn:
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()
            print("pgvector extension verified/enabled.")
        except Exception as e:
            print(f"Notice regarding extension: {e}")

    # 2. Create All Tables
    print("Creating tables in Neon...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully.")

    # 3. Seed Synthetic Data
    with Session() as db:
        print(f"Seeding {num_users} users and 12-month transaction histories...")
        stats = create_synthetic_data(db, num_users=num_users)
        print(f"Data seeding complete: {stats}")

    # 4. Generate & Index Financial PDF Contracts
    print("Generating & indexing comprehensive financial contracts...")
    # Update global connection url in settings temporarily for seeding
    os.environ["DATABASE_URL"] = database_url
    from app.core.config import settings
    settings.DATABASE_URL = database_url
    from app.db import connection
    connection.engine = engine
    connection.SessionLocal = Session

    generate_and_index_documents()
    print("Neon database initialization complete! Ready for live Render deployment.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize and seed Neon PostgreSQL database")
    parser.add_argument("--url", type=str, required=True, help="Neon PostgreSQL Connection String URL")
    parser.add_argument("--users", type=int, default=10, help="Number of users to seed (default: 10)")
    args = parser.parse_args()

    init_neon_database(args.url, num_users=args.users)
