"""The contact-form easter egg — itself a minimal intake agent.

qualify → (one clarifying question if vague) → create lead → draft an email to
the owner. Deterministic by default (no key needed); the decisions are persisted
on the lead row so the site can say "this contact form is also an agent — inspect
its decisions here." The LLM proposes the draft; we dispose (store + would-email).
"""

from __future__ import annotations

import uuid
from typing import Any

from .service import get_store


async def handle_contact(payload: dict[str, Any]) -> dict[str, Any]:
    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip()
    message = (payload.get("message") or "").strip()
    process = (payload.get("process") or "").strip()
    trace_id = f"trc_{uuid.uuid4().hex[:10]}"

    # qualify
    qualified = bool(email) and len(message) >= 10
    # one clarifying question when the prospect's process is vague
    clarifying = None
    if qualified and not process:
        clarifying = "Which business process would you most want to automate first?"

    email_draft = (
        f"Subject: New Adjuster Zero lead — {name or 'prospect'}\n\n"
        f"From: {name or 'anonymous'} <{email or 'no-email'}>\n"
        f"Process of interest: {process or '(to be clarified)'}\n\n"
        f"Message:\n{message or '(none)'}\n\n"
        f"— drafted by the contact agent ({'qualified' if qualified else 'unqualified'})."
    )

    lead = {
        "name": name, "email": email, "message": message, "process": process,
        "qualified": qualified, "clarifying_question": clarifying,
        "email_draft": email_draft, "trace_id": trace_id,
    }
    await get_store().create_lead(lead)

    return {
        "qualified": qualified,
        "clarifying_question": clarifying,
        "email_draft": email_draft,
        "decisions": [
            {"step": "qualify", "result": "qualified" if qualified else "unqualified",
             "why": "email present and message ≥ 10 chars"},
            {"step": "clarify", "result": clarifying or "no clarification needed"},
            {"step": "draft_email", "result": "email drafted to owner"},
        ],
        "trace_id": trace_id,
    }
