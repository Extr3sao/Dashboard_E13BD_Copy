import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests

from src.core.config_loader import ConfigLoader


OPENROUTER_RUNTIME_EXCEPTIONS = (
    requests.RequestException,
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    json.JSONDecodeError,
)


def _env_flag(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class OpenRouterSettings:
    enabled: bool
    api_key: str
    model: str
    timeout_ms: int
    base_url: str
    discover_free_model: bool

    @classmethod
    def from_config(cls, config: Optional[ConfigLoader] = None) -> "OpenRouterSettings":
        config = config or ConfigLoader()
        model = (
            config.get_env_var("OPENROUTER_MODEL")
            or config.get_env_var("AI_MODEL")
            or ""
        ).strip()
        timeout_raw = config.get_env_var("OPENROUTER_TIMEOUT_MS", "30000")
        try:
            timeout_ms = max(1000, int(timeout_raw))
        except (TypeError, ValueError):
            timeout_ms = 30000
        return cls(
            enabled=_env_flag(config.get_env_var("OPENROUTER_ENABLED"), default=False),
            api_key=(config.get_env_var("OPENROUTER_API_KEY", "") or "").strip(),
            model=model,
            timeout_ms=timeout_ms,
            base_url=(config.get_env_var("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1") or "https://openrouter.ai/api/v1").rstrip("/"),
            discover_free_model=_env_flag(config.get_env_var("OPENROUTER_DISCOVER_FREE_MODEL"), default=False),
        )


class OpenRouterClient:
    def __init__(
        self,
        settings: Optional[OpenRouterSettings] = None,
        session: Optional[requests.sessions.Session] = None,
        config: Optional[ConfigLoader] = None,
    ) -> None:
        self.config = config or ConfigLoader()
        self.settings = settings or OpenRouterSettings.from_config(self.config)
        self.session = session or requests.Session()

    def is_enabled(self) -> bool:
        return bool(self.settings.enabled and self.settings.api_key)

    def list_models(self) -> List[Dict[str, Any]]:
        response = self.session.get(
            f"{self.settings.base_url}/models",
            timeout=max(1, self.settings.timeout_ms / 1000),
        )
        response.raise_for_status()
        data = response.json()
        return list(data.get("data") or [])

    def select_model(self) -> Tuple[str, Dict[str, Any]]:
        if self.settings.model:
            return self.settings.model, {"source": "configured"}

        if self.settings.discover_free_model:
            try:
                models = self.list_models()
                discovered = self._discover_featured_free_model(models)
                if discovered:
                    return discovered, {"source": "discovered"}
            except OPENROUTER_RUNTIME_EXCEPTIONS as exc:
                return "openrouter/free", {"source": "fallback", "error": str(exc)}

        return "openrouter/free", {"source": "fallback"}

    def _discover_featured_free_model(self, models: List[Dict[str, Any]]) -> Optional[str]:
        candidates: List[Tuple[float, str]] = []
        for model in models:
            model_id = str(model.get("id") or "").strip()
            if not model_id:
                continue
            if not self._is_free_model(model):
                continue
            score = self._model_score(model)
            candidates.append((score, model_id))

        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return candidates[0][1]

    def _is_free_model(self, model: Dict[str, Any]) -> bool:
        pricing = model.get("pricing") or {}
        prompt_price = str(pricing.get("prompt", "")).strip()
        completion_price = str(pricing.get("completion", "")).strip()
        if prompt_price == "0" and completion_price == "0":
            return True
        model_id = str(model.get("id") or "").lower()
        return ":free" in model_id or model_id.endswith("/free") or model_id == "openrouter/free"

    def _model_score(self, model: Dict[str, Any]) -> float:
        model_id = str(model.get("id") or "").lower()
        name = str(model.get("name") or "").lower()
        architecture = model.get("architecture") or {}
        modality = str(architecture.get("modality") or model.get("modality") or "").lower()
        input_modalities = [str(item).lower() for item in (model.get("input_modalities") or [])]
        supported_parameters = [str(item).lower() for item in (model.get("supported_parameters") or [])]
        context_length = int(model.get("context_length") or 0)

        score = 0.0
        if "featured" in str(model.get("name", "")).lower():
            score += 5.0
        if "text" in modality or not modality:
            score += 4.0
        if not input_modalities or "text" in input_modalities:
            score += 4.0
        if any(token in model_id or token in name for token in ("instruct", "chat", "assistant")):
            score += 6.0
        if any(token in supported_parameters for token in ("messages", "response_format")):
            score += 3.0
        if any(token in model_id or token in name for token in ("vision", "image", "audio", "embed", "rerank", "moderation")):
            score -= 6.0
        if context_length:
            score += min(context_length / 16000.0, 4.0)
        return score

    def chat_completion(
        self,
        system_prompt: str,
        user_payload: Dict[str, Any],
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        selected_model, selection_meta = (model, {"source": "configured"}) if model else self.select_model()
        timeout_seconds = max(1, self.settings.timeout_ms / 1000)
        models_to_try: List[Tuple[str, bool]] = [(selected_model, True)]
        if selected_model != "openrouter/free":
            models_to_try.append(("openrouter/free", False))
            models_to_try.append(("google/gemini-2.5-flash", False))

        last_error = None
        for candidate, allow_retry in models_to_try:
            attempts = 2 if allow_retry else 1
            for attempt in range(attempts):
                try:
                    content = self._chat_completion_once(
                        model=candidate,
                        system_prompt=system_prompt,
                        user_payload=user_payload,
                        timeout_seconds=timeout_seconds,
                    )
                    return {
                        "ok": True,
                        "model": candidate,
                        "status": "fallback" if candidate == "openrouter/free" and candidate != selected_model else "ok",
                        "selection": selection_meta,
                        "content": content,
                    }
                except OPENROUTER_RUNTIME_EXCEPTIONS as exc:
                    last_error = str(exc)
                    if attempt + 1 >= attempts:
                        break

        return {
            "ok": False,
            "model": "openrouter/free" if selected_model != "openrouter/free" else selected_model,
            "status": "no disponible",
            "selection": selection_meta,
            "error": last_error or "openrouter_error",
            "content": None,
        }

    def _chat_completion_once(
        self,
        model: str,
        system_prompt: str,
        user_payload: Dict[str, Any],
        timeout_seconds: float,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Antigravity",
            "X-Title": "Oracle Audit Dashboard",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        response = self.session.post(
            f"{self.settings.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
