"""Universal LLM Client with Cascading Fallback (Gemini -> Groq -> OpenAI -> Anthropic -> Local)."""
import logging
import httpx
from typing import Dict, Any, Optional, List, Tuple
from app.core.config import settings

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self):
        pass

    def get_available_providers(self) -> List[Tuple[str, str, str]]:
        """
        Returns list of configured providers in fallback priority order:
        [(provider_name, api_key, model_name), ...]
        """
        providers = []
        if settings.GEMINI_API_KEY:
            providers.append(("gemini", settings.GEMINI_API_KEY, settings.LLM_MODEL or "gemini-1.5-flash"))
        if settings.GROQ_API_KEY:
            providers.append(("groq", settings.GROQ_API_KEY, settings.LLM_MODEL or "llama-3.3-70b-versatile"))
        if settings.OPENAI_API_KEY:
            providers.append(("openai", settings.OPENAI_API_KEY, settings.LLM_MODEL or "gpt-4o-mini"))
        if settings.ANTHROPIC_API_KEY:
            providers.append(("anthropic", settings.ANTHROPIC_API_KEY, settings.LLM_MODEL or "claude-3-5-sonnet-20241022"))
        return providers

    def is_live_ai_enabled(self) -> bool:
        return len(self.get_available_providers()) > 0

    def complete(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.1) -> str:
        """
        Executes text completion with cascading failover across configured providers.
        If Gemini key is exhausted / rate-limited (429), it automatically falls back
        to Groq, then OpenAI, then Anthropic.
        """
        providers = self.get_available_providers()
        if not providers:
            return ""

        errors = []
        for provider_name, api_key, model in providers:
            try:
                if provider_name == "gemini":
                    return self._call_gemini(api_key, model, prompt, system_prompt, temperature)
                elif provider_name in ("openai", "groq"):
                    base_url = "https://api.groq.com/openai/v1" if provider_name == "groq" else "https://api.openai.com/v1"
                    return self._call_openai_compatible(base_url, api_key, model, prompt, system_prompt, temperature)
                elif provider_name == "anthropic":
                    return self._call_anthropic(api_key, model, prompt, system_prompt, temperature)
            except Exception as e:
                err_msg = f"Provider '{provider_name}' failed ({e}). Shifting to next fallback provider..."
                logger.warning(err_msg)
                errors.append(err_msg)
                continue

        logger.error(f"All live AI providers exhausted or failed: {errors}")
        return ""

    def _call_gemini(self, api_key: str, model: str, prompt: str, system_prompt: Optional[str], temperature: float) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"SYSTEM INSTRUCTIONS:\n{system_prompt}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will strictly follow these instructions."}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": 1024}
        }
        with httpx.Client(timeout=25.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    def _call_openai_compatible(self, base_url: str, api_key: str, model: str, prompt: str, system_prompt: Optional[str], temperature: float) -> str:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }
        with httpx.Client(timeout=25.0) as client:
            resp = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()

    def _call_anthropic(self, api_key: str, model: str, prompt: str, system_prompt: Optional[str], temperature: float) -> str:
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "max_tokens": 1024,
            "temperature": temperature,
            "system": system_prompt or "",
            "messages": [{"role": "user", "content": prompt}]
        }
        with httpx.Client(timeout=25.0) as client:
            resp = client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"].strip()

llm_client = LLMClient()
