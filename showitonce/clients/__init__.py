"""Thin, dependency-free clients for the NVIDIA services used by live mode.

All calls are OpenAI-compatible HTTP. Keeping the transport here means a stage never
knows whether it is talking to Token Factory, a self-hosted Cosmos endpoint on Nebius,
or a mock.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

from ..config import Settings


class ClientError(RuntimeError):
    pass


class ClientNotConfigured(ClientError):
    pass


def _request_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 90.0,
) -> dict[str, Any]:
    body = None
    all_headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        all_headers["Content-Type"] = "application/json"
    all_headers.update(headers or {})
    request = urllib.request.Request(url, data=body, headers=all_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1000]
        raise ClientError(f"{method} {url} returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ClientError(f"{method} {url} failed: {exc.reason}") from exc


def _chat_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


def _models_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return base + "/models"
    return base + "/v1/models"


def parse_json_content(content: str) -> dict[str, Any]:
    """Models occasionally wrap JSON in a markdown fence despite instructions."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ClientError(f"model did not return JSON: {content[:500]}") from exc
    if not isinstance(value, dict):
        raise ClientError("model returned JSON that is not an object")
    return value


@dataclass
class TokenFactoryClient:
    settings: Settings

    def __post_init__(self) -> None:
        if not self.settings.nebius_api_key:
            raise ClientNotConfigured("NEBIUS_API_KEY is not set")

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.nebius_api_key}"}

    @cached_property
    def model_ids(self) -> list[str]:
        data = _request_json(
            "GET",
            _models_url(self.settings.token_factory_base_url),
            headers=self.headers,
            timeout=30,
        )
        return sorted(item["id"] for item in data.get("data", []) if item.get("id"))

    def _pick(self, tiers: tuple[str, ...], explicit: str) -> str:
        if explicit:
            return explicit
        for tier in tiers:
            hits = [
                model
                for model in self.model_ids
                if "nemotron" in model.lower() and tier in model.lower()
            ]
            if hits:
                return min(hits, key=len)
        raise ClientError(
            f"no Nemotron model matched {tiers}; available: {self.model_ids[:20]}"
        )

    @property
    def fast_model(self) -> str:
        return self._pick(("nano", "super"), self.settings.nemotron_fast_model)

    @property
    def reason_model(self) -> str:
        return self._pick(("ultra", "super"), self.settings.nemotron_reason_model)

    def chat(
        self,
        prompt: str,
        *,
        tier: str = "fast",
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1200,
    ) -> str:
        model = self.fast_model if tier == "fast" else self.reason_model
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        data = _request_json(
            "POST",
            _chat_url(self.settings.token_factory_base_url),
            payload={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            headers=self.headers,
        )
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ClientError(f"unexpected chat response: {data}") from exc

    def chat_json(self, prompt: str, *, tier: str = "reason", system: str | None = None) -> dict:
        return parse_json_content(self.chat(prompt, tier=tier, system=system))


@dataclass
class CosmosReasonClient:
    settings: Settings

    def __post_init__(self) -> None:
        if not self.settings.cosmos_reason_url:
            raise ClientNotConfigured("COSMOS_REASON_URL is not set")

    @property
    def headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.cosmos_reason_api_key:
            headers["Authorization"] = f"Bearer {self.settings.cosmos_reason_api_key}"
        return headers

    def chat_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> str:
        data = _request_json(
            "POST",
            _chat_url(self.settings.cosmos_reason_url),
            payload={
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            headers=self.headers,
        )
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ClientError(f"unexpected Cosmos response: {data}") from exc

    def inspect_video_frames(
        self,
        frames: list[bytes],
        prompt: str,
        *,
        mime_type: str = "image/jpeg",
    ) -> str:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for frame in frames:
            encoded = base64.b64encode(frame).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                }
            )
        return self.chat_messages([{"role": "user", "content": content}])

    def judge(self, frames: list[bytes], prompt: str) -> dict[str, Any]:
        return parse_json_content(self.inspect_video_frames(frames, prompt))


@dataclass
class ParakeetClient:
    settings: Settings

    def __post_init__(self) -> None:
        if not self.settings.parakeet_url:
            raise ClientNotConfigured("PARAKEET_URL is not set")

    def transcribe(self, audio: bytes, filename: str = "narration.wav") -> str:
        boundary = "----showitonce" + base64.urlsafe_b64encode(filename.encode()).decode()[:12]
        parts: list[bytes] = []
        parts.append(
            (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="model"\r\n\r\n'
                "parakeet\r\n"
            ).encode()
        )
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                "Content-Type: audio/wav\r\n\r\n"
            ).encode()
        )
        parts.append(audio)
        parts.append(f"\r\n--{boundary}--\r\n".encode())
        body = b"".join(parts)
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        if self.settings.parakeet_api_key:
            headers["Authorization"] = f"Bearer {self.settings.parakeet_api_key}"
        request = urllib.request.Request(
            self.settings.parakeet_url.rstrip("/") + "/v1/audio/transcriptions",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:1000]
            raise ClientError(f"Parakeet returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ClientError(f"Parakeet request failed: {exc.reason}") from exc
        return data.get("text", "")


@dataclass
class Clients:
    """Lazily-created live clients, so mock mode never touches the network."""

    settings: Settings
    _cache: dict[str, Any] = field(default_factory=dict)

    def _get(self, name: str, factory):
        if name not in self._cache:
            self._cache[name] = factory(self.settings)
        return self._cache[name]

    @property
    def token_factory(self) -> TokenFactoryClient:
        return self._get("token_factory", TokenFactoryClient)

    @property
    def cosmos_reason(self) -> CosmosReasonClient:
        return self._get("cosmos_reason", CosmosReasonClient)

    @property
    def parakeet(self) -> ParakeetClient:
        return self._get("parakeet", ParakeetClient)

    def status_line(self, stage: str, fallback: str, detail: str = "") -> str:
        """One human-readable line for the app. Nano in live mode, deterministic otherwise."""
        if self.settings.resolved_mode != "live":
            return fallback
        try:
            prompt = (
                "You write one short, warm status line for a robot-learning app. "
                "No marketing, no emoji, at most 18 words. Return only the line.\n"
                f"Stage: {stage}\nWhat happened: {detail or fallback}"
            )
            line = self.token_factory.chat(
                prompt, tier="fast", temperature=0.4, max_tokens=80
            ).strip()
            return line or fallback
        except ClientError:
            return fallback
