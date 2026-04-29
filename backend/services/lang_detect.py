from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger("backend.lang_detect")


@dataclass(frozen=True, slots=True)
class DetectedLanguage:
    language: str
    score: float | None = None


class AzureTranslatorLanguageDetectService:
    """Detect language from text using Azure Translator (Text Translation) Detect API."""

    def __init__(
        self,
        *,
        key: str | None,
        region: str | None,
        endpoint: str = "https://api.cognitive.microsofttranslator.com",
        timeout_s: float = 5.0,
        cache_size: int = 256,
    ) -> None:
        self._key = (key or "").strip()
        self._region = (region or "").strip()
        self._endpoint = endpoint.rstrip("/")
        self._timeout_s = max(0.5, float(timeout_s))
        self._cache_size = max(0, int(cache_size))
        self._cache: dict[str, DetectedLanguage | None] = {}
        self._last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._key)

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def _cache_get(self, k: str) -> DetectedLanguage | None | object:
        if self._cache_size <= 0:
            return _MISS
        if k not in self._cache:
            return _MISS
        # Refresh LRU-ish order by reinserting
        v = self._cache.pop(k)
        self._cache[k] = v
        return v

    def _cache_put(self, k: str, v: DetectedLanguage | None) -> None:
        if self._cache_size <= 0:
            return
        if k in self._cache:
            self._cache.pop(k)
        self._cache[k] = v
        # Evict oldest
        while len(self._cache) > self._cache_size:
            self._cache.pop(next(iter(self._cache)))

    def detect(self, text: str) -> DetectedLanguage | None:
        """Return detected language (e.g. 'cs', 'sk', 'en') or None on failure."""
        if not self._key:
            self._last_error = "Azure Translator is not configured (missing AZURE_TRANSLATOR_KEY)."
            return None

        raw = (text or "").strip()
        if len(raw) < 3:
            self._last_error = None
            return None

        cache_key = raw[:200].lower()
        cached = self._cache_get(cache_key)
        if cached is not _MISS:
            self._last_error = None
            return cached  # may be None

        url = f"{self._endpoint}/detect"
        params = {"api-version": "3.0"}
        headers = {
            "Ocp-Apim-Subscription-Key": self._key,
            "Content-Type": "application/json",
        }
        # For Cognitive Services resources (not global Translator), region header is required.
        if self._region:
            headers["Ocp-Apim-Subscription-Region"] = self._region

        body = [{"text": raw[:5000]}]

        try:
            with httpx.Client(timeout=self._timeout_s) as client:
                resp = client.post(url, params=params, headers=headers, json=body)
                resp.raise_for_status()
                data: Any = resp.json()
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            self._last_error = msg
            logger.warning("Translator detect failed: %s", msg)
            self._cache_put(cache_key, None)
            return None

        detected = _parse_translator_detect(data)
        self._last_error = None
        self._cache_put(cache_key, detected)
        return detected


_MISS = object()


def _parse_translator_detect(data: Any) -> DetectedLanguage | None:
    # Expected: [{"language":"cs","score":0.96,"isTranslationSupported":true,...}]
    if not isinstance(data, list) or not data:
        return None
    item = data[0]
    if not isinstance(item, dict):
        return None
    lang = item.get("language")
    if not isinstance(lang, str) or not lang.strip():
        return None
    score = item.get("score")
    if isinstance(score, (int, float)):
        score_f = float(score)
    else:
        score_f = None
    return DetectedLanguage(language=lang.strip().lower(), score=score_f)

