"""SQLAlchemy Models for Relational & Analytical Entities."""
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Numeric, Date, 
    DateTime, ForeignKey, UniqueConstraint, CheckConstraint, JSON
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    budgets = relationship("Budget", back_populates="user", cascade="all, delete-orphan")
    bills = relationship("Bill", back_populates="user", cascade="all, delete-orphan")
    goals = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")

class Account(Base):
    __tablename__ = "accounts"

    account_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    account_type = Column(String(20), nullable=False)  # savings, current, credit_card, loan
    bank_name = Column(String(100))
    opening_balance = Column(Numeric(14, 2), default=0.0)

    user = relationship("User", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account", cascade="all, delete-orphan")

class Category(Base):
    __tablename__ = "categories"

    category_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)
    type = Column(String(20), nullable=False)  # income, expense

    transactions = relationship("Transaction", back_populates="category")
    budgets = relationship("Budget", back_populates="category")

class Transaction(Base):
    __tablename__ = "transactions"

    txn_id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.account_id", ondelete="CASCADE"), nullable=False)
    txn_date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    direction = Column(String(10), nullable=False)  # debit, credit
    category_id = Column(Integer, ForeignKey("categories.category_id"), nullable=True)
    merchant = Column(String(150), nullable=True)
    description = Column(Text, nullable=True)
    source_hash = Column(String(64), unique=True, nullable=True)

    user = relationship("User", back_populates="transactions")
    account = relationship("Account", back_populates="transactions")
    category = relationship("Category", back_populates="transactions")

class Budget(Base):
    __tablename__ = "budgets"

    budget_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.category_id"), nullable=False)
    month = Column(Date, nullable=False)  # 1st of month
    limit_amount = Column(Numeric(14, 2), nullable=False)

    user = relationship("User", back_populates="budgets")
    category = relationship("Category", back_populates="budgets")
    __table_args__ = (UniqueConstraint("user_id", "category_id", "month", name="uq_user_cat_month"),)

class Bill(Base):
    __tablename__ = "bills"

    bill_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    due_date = Column(Date, nullable=False)
    status = Column(String(20), default="pending")  # paid, pending, overdue

    user = relationship("User", back_populates="bills")

class Goal(Base):
    __tablename__ = "goals"

    goal_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=False)
    target_amount = Column(Numeric(14, 2), nullable=False)
    target_date = Column(Date, nullable=True)

    user = relationship("User", back_populates="goals")

class Document(Base):
    __tablename__ = "documents"

    doc_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    doc_type = Column(String(50))  # statement, loan, insurance, other
    content_hash = Column(String(64), unique=True, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default="processed")

    user = relationship("User", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")

class Chunk(Base):
    __tablename__ = "chunks"

    chunk_id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    doc_id = Column(Integer, ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False)
    page_number = Column(Integer, nullable=False)
    section_title = Column(String(255), nullable=True)
    text = Column(Text, nullable=False)
    tsv = Column(Text, nullable=True)
    embedding = Column(JSON, nullable=True)  # Store vector as JSON list for SQLite compatibility or PG
    chunk_hash = Column(String(64), nullable=True)

    document = relationship("Document", back_populates="chunks")

class Trace(Base):
    __tablename__ = "traces"

    trace_id = Column(String(36), primary_key=True)
    user_id = Column(Integer, nullable=True)
    question = Column(Text, nullable=False)
    route = Column(String(20))  # sql, documents, both, clarify, refuse
    tool_calls = Column(JSON, default=list)
    final_answer = Column(JSON, default=dict)
    latency_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class EvalCase(Base):
    __tablename__ = "eval_cases"

    case_id = Column(Integer, primary_key=True, autoincrement=True)
    suite = Column(String(50), nullable=False)  # sql, retrieval, routing, citation, e2e, safety
    question = Column(Text, nullable=False)
    expected = Column(JSON, nullable=False)
    source = Column(String(20), default="manual")

class EvalRun(Base):
    __tablename__ = "eval_runs"

    run_id = Column(Integer, primary_key=True, autoincrement=True)
    config_name = Column(String(50), nullable=False)
    git_commit = Column(String(40), nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    metrics = Column(JSON, default=dict)

class Feedback(Base):
    __tablename__ = "feedback"

    feedback_id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(36), ForeignKey("traces.trace_id"), nullable=False)
    rating = Column(String(10), nullable=False)  # up, down
    correction = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
