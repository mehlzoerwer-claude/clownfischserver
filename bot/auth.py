#!/usr/bin/env python3
"""
🐠 Clownfischserver – Role-Based Access Control
Author:  Mehlzoerwer-Claude (https://github.com/mehlzoerwer-claude)
License: GPL-3.0

Implements DSGVO Art. 32 access control:
- operator: full execution rights (/shell, /code, /run, /ja, /ssh, /snapshot)
- approver: can approve pending operations (/ja)
- viewer:   read-only access (/status, /snapshots, /help)

Backwards compatible: if no role env vars are set but TELEGRAM_CHAT_ID
is configured, that user is auto-granted the operator role.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

ROLE_OPERATOR = "operator"
ROLE_APPROVER = "approver"
ROLE_VIEWER = "viewer"

VALID_ROLES = (ROLE_OPERATOR, ROLE_APPROVER, ROLE_VIEWER)

# Operators implicitly hold approver + viewer rights.
# Approvers implicitly hold viewer rights.
_ROLE_INHERITANCE: dict[str, tuple[str, ...]] = {
    ROLE_OPERATOR: (ROLE_OPERATOR, ROLE_APPROVER, ROLE_VIEWER),
    ROLE_APPROVER: (ROLE_APPROVER, ROLE_VIEWER),
    ROLE_VIEWER: (ROLE_VIEWER,),
}


def _parse_id_list(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def _load_role_map() -> dict[str, str]:
    """Read role config from env vars.

    Returns {user_id_str: highest_role}. If a user appears in multiple
    role lists, the strongest role wins (operator > approver > viewer).
    """
    operators = _parse_id_list(os.getenv("CLOWNFISCH_OPERATORS"))
    approvers = _parse_id_list(os.getenv("CLOWNFISCH_APPROVERS"))
    viewers = _parse_id_list(os.getenv("CLOWNFISCH_VIEWERS"))

    role_map: dict[str, str] = {}

    for uid in viewers:
        role_map[uid] = ROLE_VIEWER
    for uid in approvers:
        role_map[uid] = ROLE_APPROVER
    for uid in operators:
        role_map[uid] = ROLE_OPERATOR

    # Backwards compatibility: legacy TELEGRAM_CHAT_ID becomes operator
    # when no explicit role lists are defined.
    if not role_map:
        legacy = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if legacy:
            role_map[legacy] = ROLE_OPERATOR
            logger.info(
                "Auth: no role lists configured – granting operator to legacy "
                "TELEGRAM_CHAT_ID for backwards compatibility."
            )

    return role_map


def get_role(user_id: str | int | None) -> str | None:
    """Return the role of a user, or None if unauthorized."""
    if user_id is None:
        return None
    return _load_role_map().get(str(user_id))


def has_role(user_id: str | int | None, *required: str) -> bool:
    """Check if the user satisfies ANY of the required roles.

    Inheritance applies: an operator passes a check for approver/viewer.
    """
    role = get_role(user_id)
    if role is None:
        return False
    granted = _ROLE_INHERITANCE.get(role, (role,))
    return any(r in granted for r in required)


def is_authorized(user_id: str | int | None) -> bool:
    """True if the user has any role at all."""
    return get_role(user_id) is not None


def list_users_with_role(role: str) -> list[str]:
    """Return all user_ids that hold (or inherit) the given role."""
    if role not in VALID_ROLES:
        return []
    return [uid for uid, r in _load_role_map().items()
            if role in _ROLE_INHERITANCE.get(r, (r,))]


def describe_roles() -> dict[str, list[str]]:
    """Snapshot of current role assignments – useful for /status or audits."""
    role_map = _load_role_map()
    result: dict[str, list[str]] = {r: [] for r in VALID_ROLES}
    for uid, role in role_map.items():
        result[role].append(uid)
    return result
