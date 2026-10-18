"""Literal, numeric, role, and modality validation (Guide §9.1 and §9.2).

Ensures:
- Every number, amount, duration in a RESTATEMENT appears in the cited text (no hallucinated figures).
- No unit conversions (e.g. 60 days != 2 months).
- Role canonicalization: TENANT vs LANDLORD. Swapped roles are rejected (T-CITE-ROLE-01).
- Modality & negation consistency.
"""
from __future__ import annotations

import re
from typing import List, Set, Tuple
from backend.app.agent.schema import ModelPoint

# Role canonicalization sets
_TENANT_WORDS = frozenset([
    "tenant", "tenants", "lessee", "lessees", "licensee", "licensees",
    "occupant", "occupants", "second party",
])
_LANDLORD_WORDS = frozenset([
    "landlord", "landlords", "lessor", "lessors", "licensor", "licensors",
    "owner", "owners", "first party",
])

# Extract numeric literals: digits, rupee amounts, commas
_NUMBER_RE = re.compile(r"\b(?:\$|Rs\.?|INR|₹)?\s*(\d+(?:,\d+)*(?:\.\d+)?)\b")

# Modality verbs
_MODAL_OBLIGATION = frozenset(["must", "shall", "required to", "obligated to", "will"])
_MODAL_PERMISSION = frozenset(["may", "permitted to", "allowed to", "can"])
_MODAL_PROHIBITION = frozenset(["shall not", "must not", "may not", "cannot", "prohibited", "not allowed"])


def canonicalize_roles(text: str) -> Set[str]:
    """Return set of canonical roles ('TENANT', 'LANDLORD') mentioned in text."""
    lower = text.lower()
    roles = set()
    for word in _TENANT_WORDS:
        if re.search(r"\b" + re.escape(word) + r"\b", lower):
            roles.add("TENANT")
            break
    for word in _LANDLORD_WORDS:
        if re.search(r"\b" + re.escape(word) + r"\b", lower):
            roles.add("LANDLORD")
            break
    return roles


def extract_numbers(text: str) -> Set[str]:
    """Extract normalised numeric values from text."""
    numbers = set()
    for match in _NUMBER_RE.finditer(text):
        num_str = match.group(1).replace(",", "")
        numbers.add(num_str)
    return numbers


def _extract_actor_obligations(text: str) -> List[Tuple[str, str]]:
    """
    Extract simple (ROLE, MODALITY) pairings from text,
    e.g. 'tenant shall' -> ('TENANT', 'OBLIGATION').
    """
    lower = text.lower()
    pairings: List[Tuple[str, str]] = []

    # Patterns for prohibition
    for role_word in _TENANT_WORDS | _LANDLORD_WORDS:
        canonical = "TENANT" if role_word in _TENANT_WORDS else "LANDLORD"
        # Prohibition
        if re.search(r"\b" + re.escape(role_word) + r"\s+(?:shall\s+not|must\s+not|may\s+not|cannot)\b", lower):
            pairings.append((canonical, "PROHIBITION"))
        # Obligation
        elif re.search(r"\b" + re.escape(role_word) + r"\s+(?:shall|must|is\s+required\s+to|will)\b", lower):
            pairings.append((canonical, "OBLIGATION"))
        # Permission
        elif re.search(r"\b" + re.escape(role_word) + r"\s+(?:may|can|is\s+permitted\s+to)\b", lower):
            pairings.append((canonical, "PERMISSION"))

    return pairings


def validate_restatement(
    point: ModelPoint,
    cited_texts: List[str],
) -> Tuple[bool, str]:
    """
    Validate a RESTATEMENT point against the text of cited sentences.

    Checks:
    1. Role Swap Check (T-CITE-ROLE-01): Roles named in the restatement must occur
       in the cited text; actor obligations must not be inverted.
    2. Numbers & Amounts: Every number in the restatement must be present in cited sentences.
    3. Unit Conversions: Reject unauthorized conversions.
    """
    combined_source = " ".join(cited_texts)
    restatement_text = point.text

    # 1. Role Consistency (T-CITE-ROLE-01)
    restate_roles = canonicalize_roles(restatement_text)
    source_roles = canonicalize_roles(combined_source)

    # All roles named in restatement must exist in cited sentences
    for role in restate_roles:
        if role not in source_roles:
            return False, f"Role '{role}' named in restatement does not exist in cited source text (T-CITE-ROLE-01)."

    # Check for swapped obligations (e.g. Tenant obligation transferred to Landlord)
    restate_pairs = _extract_actor_obligations(restatement_text)
    source_pairs = _extract_actor_obligations(combined_source)

    for r_role, r_mod in restate_pairs:
        # If the other role had this obligation in source, role was swapped
        opposite_role = "LANDLORD" if r_role == "TENANT" else "TENANT"
        if (opposite_role, r_mod) in source_pairs and (r_role, r_mod) not in source_pairs:
            return False, f"Role swap detected: {r_role} assigned obligation of {opposite_role} (T-CITE-ROLE-01)."

    # 2. Number Verification
    restate_nums = extract_numbers(restatement_text)
    source_nums = extract_numbers(combined_source)

    for num in restate_nums:
        if num not in source_nums:
            return False, f"Numeric value '{num}' in restatement not found in cited sentences."

    # 3. Unit Conversion Protection: Reject words like 'months' if source only contains 'days'
    restate_lower = restatement_text.lower()
    source_lower = combined_source.lower()
    if ("month" in restate_lower or "months" in restate_lower) and ("month" not in source_lower and "months" not in source_lower):
        if "day" in source_lower or "days" in source_lower:
            return False, "Unauthorized unit conversion: converted days to months."

    return True, "Valid restatement"
