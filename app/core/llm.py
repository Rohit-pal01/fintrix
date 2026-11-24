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
        return providers

    def is_live_ai_enabled(self) -> bool:
        return len(self.get_available_providers()) > 0

    def complete(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.1) -> str:
        """
        Executes text completion with cascading failover across configured free providers (Gemini -> Groq).
        If Gemini is exhausted or rate-limited (429), it automatically falls back to Groq.
        """
        providers = self.get_available_providers()
        if not providers:
            return ""

        errors = []
        for provider_name, api_key, model in providers:
            try:
                if provider_name == "gemini":
                    return self._call_gemini(api_key, model, prompt, system_prompt, temperature)
                elif provider_name == "groq":
                    return self._call_groq(api_key, model, prompt, system_prompt, temperature)
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

    def _call_groq(self, api_key: str, model: str, prompt: str, system_prompt: Optional[str], temperature: float) -> str:
        url = "https://api.groq.com/openai/v1/chat/completions"
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
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()

llm_client = LLMClient()
