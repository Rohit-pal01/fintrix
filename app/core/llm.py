"""Universal LLM Client supporting Gemini, OpenAI, Groq, Anthropic, Ollama, and Mock."""
import json
import logging
import httpx
from typing import Dict, Any, Optional, List
from app.core.config import settings

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.model = settings.LLM_MODEL

        # Auto-detect provider based on available keys if set to "auto"
        if self.provider == "auto":
            if settings.GEMINI_API_KEY:
                self.provider = "gemini"
                self.model = self.model or "gemini-1.5-flash"
            elif settings.OPENAI_API_KEY:
                self.provider = "openai"
                self.model = self.model or "gpt-4o-mini"
            elif settings.GROQ_API_KEY:
                self.provider = "groq"
                self.model = self.model or "llama-3.3-70b-versatile"
            elif settings.ANTHROPIC_API_KEY:
                self.provider = "anthropic"
                self.model = self.model or "claude-3-5-sonnet-20241022"
            elif settings.LLM_API_KEY:
                self.provider = "openai"
                self.model = self.model or "gpt-4o-mini"
            else:
                self.provider = "mock"

    def is_live_ai_enabled(self) -> bool:
        return self.provider != "mock"

    def complete(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.1) -> str:
        """Synchronous text completion across AI providers."""
        if not self.is_live_ai_enabled():
            return ""

        try:
            if self.provider == "gemini":
                return self._call_gemini(prompt, system_prompt, temperature)
            elif self.provider in ("openai", "groq"):
                return self._call_openai_compatible(prompt, system_prompt, temperature)
            elif self.provider == "anthropic":
                return self._call_anthropic(prompt, system_prompt, temperature)
            elif self.provider == "ollama":
                return self._call_ollama(prompt, system_prompt, temperature)
        except Exception as e:
            logger.error(f"Live LLM call failed on provider {self.provider}: {e}")
            return ""
        return ""

    def _call_gemini(self, prompt: str, system_prompt: Optional[str], temperature: float) -> str:
        key = settings.GEMINI_API_KEY or settings.LLM_API_KEY
        model = self.model or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"SYSTEM INSTRUCTIONS:\n{system_prompt}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will strictly follow these instructions."}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": 1024}
        }

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    def _call_openai_compatible(self, prompt: str, system_prompt: Optional[str], temperature: float) -> str:
        if self.provider == "groq":
            key = settings.GROQ_API_KEY or settings.LLM_API_KEY
            base_url = settings.LLM_BASE_URL or "https://api.groq.com/openai/v1"
            model = self.model or "llama-3.3-70b-versatile"
        else:
            key = settings.OPENAI_API_KEY or settings.LLM_API_KEY
            base_url = settings.LLM_BASE_URL or "https://api.openai.com/v1"
            model = self.model or "gpt-4o-mini"

        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()

    def _call_anthropic(self, prompt: str, system_prompt: Optional[str], temperature: float) -> str:
        key = settings.ANTHROPIC_API_KEY or settings.LLM_API_KEY
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model or "claude-3-5-sonnet-20241022",
            "max_tokens": 1024,
            "temperature": temperature,
            "system": system_prompt or "",
            "messages": [{"role": "user", "content": prompt}]
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"].strip()

    def _call_ollama(self, prompt: str, system_prompt: Optional[str], temperature: float) -> str:
        base_url = settings.LLM_BASE_URL or "http://localhost:11434"
        payload = {
            "model": self.model or "llama3",
            "prompt": prompt,
            "system": system_prompt or "",
            "stream": False,
            "options": {"temperature": temperature}
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{base_url}/api/generate", json=payload)
            resp.raise_for_status()
            return resp.json().get("response", "").strip()

llm_client = LLMClient()
