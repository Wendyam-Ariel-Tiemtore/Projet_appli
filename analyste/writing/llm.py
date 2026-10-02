"""Fournisseurs de modèles de langage : local (Ollama), Claude (API Anthropic, option), ou aucun.

Règle de confidentialité : le modèle ne reçoit jamais les données brutes, seulement des résultats agrégés
(paragraphes de résultats déjà calculés, intitulés de variables) et le texte saisi par l'utilisateur.
"""

from __future__ import annotations

import httpx

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class LLMError(RuntimeError):
    pass


class Provider:
    name = "aucun"
    external = False

    def available(self) -> bool:
        return False

    def complete(self, system: str, prompt: str, max_tokens: int = 1800) -> str:  # pragma: no cover
        raise LLMError("Aucun modèle de langage configuré.")


class NoProvider(Provider):
    pass


class OllamaProvider(Provider):
    """Modèle exécuté localement par Ollama : aucune donnée ne quitte la machine."""

    name = "local (Ollama)"
    external = False

    def __init__(self, base_url: str, model: str, timeout: float = 600.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def available(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=3.0)
            r.raise_for_status()
            names = {m.get("name", "") for m in r.json().get("models", [])}
            return any(n == self.model or n.split(":")[0] == self.model.split(":")[0] for n in names)
        except (httpx.HTTPError, ValueError):
            return False

    def complete(self, system: str, prompt: str, max_tokens: int = 1800) -> str:
        body = {"model": self.model, "stream": False,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                "options": {"temperature": 0.2, "num_predict": max_tokens}}
        try:
            r = httpx.post(f"{self.base_url}/api/chat", json=body, timeout=self.timeout)
            r.raise_for_status()
            return r.json()["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise LLMError(f"Échec de l'appel au modèle local ({type(exc).__name__}).") from exc


class AnthropicProvider(Provider):
    """API Claude : ne reçoit que des résultats agrégés, après consentement explicite de l'utilisateur."""

    name = "Claude (API Anthropic)"
    external = True

    def __init__(self, api_key: str, model: str, timeout: float = 180.0):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.api_key)

    def complete(self, system: str, prompt: str, max_tokens: int = 1800) -> str:
        headers = {"x-api-key": self.api_key, "anthropic-version": ANTHROPIC_VERSION,
                   "content-type": "application/json"}
        body = {"model": self.model, "max_tokens": max_tokens, "temperature": 0.2, "system": system,
                "messages": [{"role": "user", "content": prompt}]}
        try:
            r = httpx.post(ANTHROPIC_URL, headers=headers, json=body, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise LLMError(f"Échec de l'appel à l'API Claude ({type(exc).__name__}).") from exc


def make_provider(settings, choice: str, user_api_key: str | None = None) -> Provider:
    """choice : 'local' | 'claude' | 'aucun'."""
    if choice == "local":
        return OllamaProvider(settings.ollama_url, settings.ollama_model)
    if choice == "claude":
        key = user_api_key or settings.anthropic_api_key
        if key:
            return AnthropicProvider(key, settings.anthropic_model)
    return NoProvider()
