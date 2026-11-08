"""Small AI provider interface for the personal companion app.

Supports:
- gemini: Google Gen AI SDK (google-genai)
- openai/openai_compatible/ollama: OpenAI-compatible chat completions over HTTP

Config is read from environment/config (backward compatible with GEMINI_API_KEY/RECAP_MODEL).
"""

from __future__ import annotations

import json
import os
import time
from typing import Callable

import requests

from config import AI_API_KEY, AI_BASE_URL, AI_FALLBACK_MODEL, AI_MODEL, AI_PROVIDER, AI_TIMEOUT

try:
    from google import genai
except Exception:
    genai = None

try:
    from google.genai import types as genai_types
except Exception:
    genai_types = None


class AIProviderError(RuntimeError):
    pass


class ModelNotFoundError(AIProviderError):
    pass


def _is_model_error(err: Exception) -> bool:
    s = str(err).lower()
    if "api key" in s or "quota" in s or "rate limit" in s or "permission" in s:
        return False
    return any(x in s for x in [
        "model", "not found", "not_found", "404", "unsupported", "does not exist",
        "no longer available", "invalid model", "unknown model", "unrecognized",
    ])


class BaseProvider:
    name = "base"

    def __init__(self, api_key="", model="", base_url="", timeout=60, fallback_model=""):
        self.api_key = api_key or ""
        self.model = model or ""
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = int(timeout or 60)
        self.fallback_model = fallback_model or ""

    def is_configured(self) -> bool:
        return bool(self.model)

    def candidate_models(self, model=None):
        out = []
        for m in [model or self.model, self.fallback_model]:
            if m and m not in out:
                out.append(m)
        return out

    def generate(self, prompt, *, system=None, model=None, max_tokens=320, temperature=0.4, timeout=None, stream=False, on_chunk: Callable[[str, dict], None] | None = None):
        raise NotImplementedError


class GeminiProvider(BaseProvider):
    name = "gemini"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client = None

    def is_configured(self) -> bool:
        return bool(self.api_key) and genai is not None and bool(self.model)

    def _client_obj(self):
        if self._client is None:
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _config(self, max_tokens, temperature):
        if genai_types is None:
            return None
        try:
            return genai_types.GenerateContentConfig(max_output_tokens=int(max_tokens), temperature=float(temperature))
        except Exception:
            return None

    def candidate_models(self, model=None):
        out = []
        preferred = model or self.model
        for m in [preferred, self.fallback_model, "gemini-3.8-flash", "gemini-3.8-flash-lite", "gemini-2.5-flash"]:
            if not m:
                continue
            m = str(m).strip()
            # normalize "models/..." prefix for candidate comparison only when useful
            if m and m not in out:
                out.append(m)
        return out

    def generate(self, prompt, *, system=None, model=None, max_tokens=320, temperature=0.4, timeout=None, stream=False, on_chunk=None):
        if not self.is_configured():
            raise AIProviderError("Gemini is not configured (need GEMINI_API_KEY/AI_API_KEY and google-genai).")
        client = self._client_obj()
        timeout = int(timeout or self.timeout)
        contents = prompt if not system else f"{system}\n\n{prompt}"
        config = self._config(max_tokens, temperature)
        last_err = None
        started = time.time()
        for m in self.candidate_models(model):
            try:
                text = ""
                if stream:
                    for chunk in client.models.generate_content_stream(model=m, contents=contents, config=config):
                        part = getattr(chunk, "text", None)
                        if part:
                            text += part
                            if on_chunk:
                                on_chunk(text, {"model": m, "provider": self.name})
                        if time.time() - started > timeout:
                            raise AIProviderError(f"AI request timed out ({timeout}s).")
                    if text.strip():
                        return {"text": text.strip(), "model": m, "provider": self.name}
                resp = client.models.generate_content(model=m, contents=contents, config=config)
                text = getattr(resp, "text", None) or ""
                if text.strip():
                    return {"text": text.strip(), "model": m, "provider": self.name}
                last_err = AIProviderError("No text generated.")
            except Exception as e:
                last_err = e
                if _is_model_error(e):
                    continue
                if stream and 'text' in locals() and text.strip():
                    return {"text": text.strip(), "model": m, "provider": self.name}
                raise AIProviderError(str(e)) from e
        if last_err:
            if _is_model_error(last_err):
                raise ModelNotFoundError(str(last_err)) from last_err
            raise AIProviderError(str(last_err)) from last_err
        raise AIProviderError("No text generated.")


class OpenAICompatibleProvider(BaseProvider):
    name = "openai_compatible"

    def is_configured(self) -> bool:
        # Ollama/local servers may not require a key.
        return bool(self.model) and bool(self.base_url or self.api_key or self.name)

    def _endpoint(self):
        base = self.base_url
        if not base:
            base = "https://api.openai.com/v1"
        if base.endswith("/chat/completions"):
            return base
        return base + "/chat/completions"

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _parse_stream(self, resp, on_chunk, timeout, started, model):
        text = ""
        for raw in resp.iter_lines(decode_unicode=True):
            if time.time() - started > timeout:
                raise AIProviderError(f"AI request timed out ({timeout}s).")
            if not raw:
                continue
            line = raw.strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            choices = obj.get("choices") or []
            if not choices:
                continue
            delta = (choices[0] or {}).get("delta") or {}
            part = delta.get("content")
            if part:
                text += part
                if on_chunk:
                    on_chunk(text, {"model": model, "provider": self.name})
        return text

    def generate(self, prompt, *, system=None, model=None, max_tokens=320, temperature=0.4, timeout=None, stream=False, on_chunk=None):
        timeout = int(timeout or self.timeout)
        started = time.time()
        last_err = None
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        for m in self.candidate_models(model):
            try:
                payload = {
                    "model": m,
                    "messages": messages,
                    "temperature": float(temperature),
                    "max_tokens": int(max_tokens),
                    "stream": bool(stream),
                }
                resp = requests.post(self._endpoint(), headers=self._headers(), json=payload, timeout=timeout, stream=bool(stream))
                if resp.status_code >= 400:
                    try:
                        err = resp.json()
                    except Exception:
                        err = resp.text
                    msg = err.get("error", {}).get("message") if isinstance(err, dict) else str(err)
                    msg = msg or f"HTTP {resp.status_code}"
                    e = ModelNotFoundError(msg) if (resp.status_code == 404 or _is_model_error(Exception(msg))) else AIProviderError(msg)
                    last_err = e
                    if isinstance(e, ModelNotFoundError):
                        continue
                    raise e
                if stream:
                    text = self._parse_stream(resp, on_chunk, timeout, started, m)
                else:
                    data = resp.json()
                    text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
                if (text or "").strip():
                    return {"text": text.strip(), "model": m, "provider": self.name}
                last_err = AIProviderError("No text generated.")
            except (ModelNotFoundError, AIProviderError):
                raise
            except Exception as e:
                last_err = e
                if _is_model_error(e):
                    continue
                raise AIProviderError(str(e)) from e
        if last_err:
            raise last_err
        raise AIProviderError("No text generated.")


_provider = None


def create_provider():
    provider = AI_PROVIDER
    key = AI_API_KEY
    model = AI_MODEL
    base = AI_BASE_URL
    timeout = AI_TIMEOUT
    fallback = AI_FALLBACK_MODEL

    if provider in ("openai", "openai_compatible", "groq", "openrouter"):
        if provider == "openrouter" and not base:
            base = "https://openrouter.ai/api/v1"
        if provider == "groq" and not base:
            base = "https://api.groq.com/openai/v1"
        return OpenAICompatibleProvider(api_key=key, model=model, base_url=base, timeout=timeout, fallback_model=fallback)
    if provider in ("ollama", "local"):
        if not base:
            base = "http://localhost:11434/v1"
        # Ollama usually needs no key; avoid sending a Gemini key to a local server.
        local_key = os.environ.get("AI_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
        return OpenAICompatibleProvider(api_key=local_key, model=model or "llama3.2", base_url=base, timeout=timeout, fallback_model=fallback)
    # default gemini
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("AI_API_KEY") or key
    return GeminiProvider(api_key=gemini_key, model=model, base_url=base, timeout=timeout, fallback_model=fallback)


def get_provider():
    global _provider
    if _provider is None:
        _provider = create_provider()
    return _provider
