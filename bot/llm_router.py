#!/usr/bin/env python3
"""
🐠 Clownfischserver – LLM Provider Router (Phase 3)
Author:  Mehlzoerwer-Claude (https://github.com/mehlzoerwer-claude)
License: GPL-3.0

Replaces the previously hard-wired Ollama+OpenRouter fallback logic with a
config-driven primary/fallback chain.

Env vars:
  LLM_PRIMARY_PROVIDER     = "ollama" | "openrouter"  (default: ollama)
  LLM_PRIMARY_MODEL        = model id for the primary provider
  LLM_PRIMARY_MODEL_FAST   = optional faster model for chat replies (ollama only)
  LLM_PRIMARY_NUM_CTX      = context window override (ollama)
  LLM_FALLBACK_PROVIDER    = "openrouter" | "ollama" | ""   ("" disables fallback)
  LLM_FALLBACK_MODEL       = model id for fallback provider
  TRACK_LLM_COSTS          = "true"|"false" – currently informational only

Backwards compatibility:
- If LLM_*_PROVIDER vars are absent we still default to Ollama primary and,
  when OPENROUTER_API_KEY exists, OpenRouter as fallback. Existing
  OLLAMA_MODEL / OLLAMA_MODEL_FAST / OLLAMA_NUM_CTX / OPENROUTER_API_KEY
  env vars are honoured.

Routing policy (intentionally explicit, not "self-improving"):
- Primary is tried first. Only routable errors (network, timeout, provider
  unavailable) trigger fallback. Hard errors (invalid JSON, malformed prompt,
  bad API key) propagate so callers see them.
- Every routing decision is written to the audit trail as `llm.route` so
  admins can see which model produced which output (DSGVO Art. 5(1)(a)
  transparency).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Awaitable, Callable, Optional

from ollama_client import OllamaClient
from openrouter_client import OpenRouterClient

try:  # audit is optional – router must work even if audit module is missing
    import audit_log
except ImportError:  # pragma: no cover
    audit_log = None  # type: ignore

logger = logging.getLogger(__name__)

PROVIDER_OLLAMA = "ollama"
PROVIDER_OPENROUTER = "openrouter"

# Error substrings that should trigger a fallback rather than propagate.
# Kept narrow on purpose – we don't want to mask programmer errors.
_ROUTABLE_ERROR_FRAGMENTS = (
    "Timeout",
    "nicht erreichbar",
    "ConnectionError",
    "Connection refused",
    "API Key nicht konfiguriert",
)


def _is_routable_error(exc: BaseException) -> bool:
    msg = str(exc)
    return any(frag in msg for frag in _ROUTABLE_ERROR_FRAGMENTS)


class LLMProvider:
    """Thin interface every provider satisfies."""

    name: str = "base"
    model: str = ""

    def is_available(self) -> bool:
        raise NotImplementedError

    async def chat(self, message: str, history: list | None = None) -> str:
        raise NotImplementedError

    async def generate_shell_command(self, description: str) -> dict:
        raise NotImplementedError

    async def explain_output(self, command: str, output: str,
                             error: str = "") -> str:
        raise NotImplementedError


class OllamaProvider(LLMProvider):
    name = PROVIDER_OLLAMA

    def __init__(self, model: Optional[str] = None,
                 model_fast: Optional[str] = None,
                 num_ctx: Optional[int] = None,
                 base_url: Optional[str] = None):
        # Pass openrouter_client=None so the underlying client does NOT
        # perform its own fallback – the router owns that decision now.
        self.client = OllamaClient(
            openrouter_client=None,
            model=model,
            model_fast=model_fast,
            num_ctx=num_ctx,
            base_url=base_url,
        )
        self.model = self.client.model

    def is_available(self) -> bool:
        # Connection health is checked at call time; we always advertise
        # ourselves as available so the router will attempt and trigger
        # fallback on actual failure.
        return True

    async def chat(self, message, history=None):
        return await self.client.chat(message, history)

    async def generate_shell_command(self, description):
        return await self.client.generate_shell_command(description)

    async def explain_output(self, command, output, error=""):
        return await self.client.explain_output(command, output, error)


class OpenRouterProvider(LLMProvider):
    name = PROVIDER_OPENROUTER

    def __init__(self, model: Optional[str] = None):
        self.client = OpenRouterClient()
        # OpenRouterClient reads OPENROUTER_API_KEY at import time. We
        # only override the model id, leaving the API key handling alone.
        self.model = model or "openrouter/free"
        if model:
            # Patch the FREE_MODELS dict so chat/coder both use the
            # configured model. Limited blast radius – it only affects
            # this OpenRouterClient instance, not the module constant.
            self._patch_model(model)

    def _patch_model(self, model: str) -> None:
        # The underlying OpenRouterClient hard-codes FREE_MODELS["coder"]/
        # ["chat"] at call sites. Wrap _chat_sync so every call resolves
        # to the user-pinned model regardless of what callers pass in.
        pinned = model
        original_chat_sync = self.client._chat_sync

        def wrapper(messages, system=None, model=None):
            return original_chat_sync(messages, system=system, model=pinned)

        self.client._chat_sync = wrapper  # type: ignore[assignment]

    def is_available(self) -> bool:
        return self.client.is_available()

    async def chat(self, message, history=None):
        return await self.client.chat(message, history)

    async def generate_shell_command(self, description):
        return await self.client.generate_shell_command(description)

    async def explain_output(self, command, output, error=""):
        return await self.client.explain_output(command, output, error)


def _build_provider(kind: str) -> Optional[LLMProvider]:
    """Build the provider for kind ∈ {"primary", "fallback"}.

    Returns None if the configuration disables this tier (e.g. fallback
    requested but no key available).
    """
    explicit = os.getenv(f"LLM_{kind.upper()}_PROVIDER", "").strip().lower()

    if kind == "primary":
        provider_name = explicit or PROVIDER_OLLAMA
    else:
        # Fallback default: openrouter only if API key is configured.
        if explicit:
            provider_name = explicit
        elif os.getenv("OPENROUTER_API_KEY"):
            provider_name = PROVIDER_OPENROUTER
        else:
            return None

    if provider_name in ("", "none", "off", "disabled"):
        return None

    model = os.getenv(f"LLM_{kind.upper()}_MODEL", "").strip() or None

    if provider_name == PROVIDER_OLLAMA:
        model_fast = os.getenv(f"LLM_{kind.upper()}_MODEL_FAST", "").strip() or None
        num_ctx_raw = os.getenv(f"LLM_{kind.upper()}_NUM_CTX", "").strip()
        num_ctx = int(num_ctx_raw) if num_ctx_raw.isdigit() else None
        return OllamaProvider(model=model, model_fast=model_fast,
                              num_ctx=num_ctx)
    if provider_name == PROVIDER_OPENROUTER:
        provider = OpenRouterProvider(model=model)
        # Skip the tier if OpenRouter is configured but key is missing.
        if not provider.is_available():
            logger.warning(
                f"LLM router: {kind} provider 'openrouter' has no API key – disabled"
            )
            return None
        return provider

    logger.error(f"LLM router: unknown {kind} provider '{provider_name}'")
    return None


_BUILD_FROM_ENV = object()  # sentinel: distinguish "not passed" from "None"


class LLMRouter:
    """Drop-in replacement for the old OllamaClient surface.

    Exposes the same async methods (`chat`, `generate_shell_command`,
    `explain_output`) plus a small status surface (`primary`, `fallback`,
    `describe()`).

    Pass `primary=None` / `fallback=None` to explicitly disable a tier;
    omit the kwarg entirely to build the tier from environment.
    """

    def __init__(self, primary=_BUILD_FROM_ENV, fallback=_BUILD_FROM_ENV):
        self.primary = _build_provider("primary") if primary is _BUILD_FROM_ENV else primary
        self.fallback = _build_provider("fallback") if fallback is _BUILD_FROM_ENV else fallback
        if self.primary is None and self.fallback is None:
            logger.error("LLMRouter: neither primary nor fallback configured!")

    # ---- public describe ------------------------------------------------
    def describe(self) -> dict:
        def _info(p: LLMProvider | None) -> dict | None:
            if p is None:
                return None
            return {"provider": p.name, "model": p.model,
                    "available": p.is_available()}
        return {"primary": _info(self.primary), "fallback": _info(self.fallback)}

    # ---- dispatcher -----------------------------------------------------
    async def _dispatch(self, method_name: str, *args, **kwargs) -> Any:
        attempts: list[tuple[str, LLMProvider]] = []
        if self.primary is not None:
            attempts.append(("primary", self.primary))
        if self.fallback is not None:
            attempts.append(("fallback", self.fallback))

        if not attempts:
            raise RuntimeError(
                "Kein LLM-Provider konfiguriert (LLM_PRIMARY_PROVIDER fehlt)"
            )

        last_error: Optional[BaseException] = None
        for tier, provider in attempts:
            if not provider.is_available():
                self._audit("skip", tier, provider, method_name,
                            reason="provider_unavailable")
                continue
            try:
                result = await getattr(provider, method_name)(*args, **kwargs)
                self._audit("hit", tier, provider, method_name)
                return result
            except Exception as e:
                last_error = e
                routable = _is_routable_error(e)
                self._audit("error", tier, provider, method_name,
                            reason=str(e)[:200],
                            routable=routable)
                if not routable:
                    # Hard error – don't mask it with a fallback.
                    raise
                # Otherwise loop to next tier.
                continue

        # All tiers exhausted.
        raise RuntimeError(
            f"Alle LLM-Provider fehlgeschlagen für {method_name}: {last_error}"
        )

    def _audit(self, status: str, tier: str, provider: LLMProvider,
               method: str, **extra) -> None:
        if audit_log is None:
            return
        try:
            details = {"tier": tier, "provider": provider.name,
                       "model": provider.model, "method": method}
            details.update(extra)
            audit_log.log_action(None, "llm.route", result=status,
                                 details=details)
        except Exception as e:  # pragma: no cover – audit must never fail
            logger.debug(f"audit emit failed: {e}")

    # ---- public surface -------------------------------------------------
    async def chat(self, message: str, history: list | None = None) -> str:
        return await self._dispatch("chat", message, history)

    async def generate_shell_command(self, description: str) -> dict:
        return await self._dispatch("generate_shell_command", description)

    async def explain_output(self, command: str, output: str,
                             error: str = "") -> str:
        return await self._dispatch("explain_output", command, output, error)

    # ---- convenience for the warmup path in bot.py ----------------------
    @property
    def ollama_models(self) -> list[str]:
        """Return distinct Ollama model ids configured across tiers –
        used by the warmup thread in bot.py."""
        models: list[str] = []
        for p in (self.primary, self.fallback):
            if isinstance(p, OllamaProvider):
                if p.client.model and p.client.model not in models:
                    models.append(p.client.model)
                if (p.client.model_fast
                        and p.client.model_fast not in models):
                    models.append(p.client.model_fast)
        return models

    @property
    def ollama_base_url(self) -> str:
        for p in (self.primary, self.fallback):
            if isinstance(p, OllamaProvider):
                return p.client.base_url
        return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    def has_fallback(self) -> bool:
        return self.fallback is not None and self.fallback.is_available()
