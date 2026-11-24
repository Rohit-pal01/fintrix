"""Application Configuration with Universal LLM & Database Support."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App info
    APP_NAME: str = "Verifiable Finance Copilot"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Databases (Supports Neon PostgreSQL & local SQLite)
    DATABASE_URL: str = "sqlite:///./finance_copilot.db"
    READONLY_DATABASE_URL: Optional[str] = None

    # LLM Settings (Free Providers: Gemini & Groq)
    LLM_PROVIDER: str = "auto"  # auto | gemini | groq
    LLM_MODEL: Optional[str] = None
    
    # Free Provider API Keys
    GEMINI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    
    # Generic API Key / Base URL
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None

    # Embedding Settings
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIM: int = 384

    # Agent Limits
    MAX_STEPS: int = 6
    STATEMENT_TIMEOUT_SECONDS: int = 5
    MAX_RETRY_ATTEMPTS: int = 2
    MAX_QUERY_ROWS: int = 100

settings = Settings()
