"""ADK tools for the audit domain — lead fetching, audit persistence, discovery."""

import json
from typing import Any

from infra.logging import get_logger

logger = get_logger(__name__)


def get_pending_audits(limit: int = 20) -> dict[str, Any]:
    """Fetch leads that have not yet been audited from the database.

    Args:
        limit: Maximum number of leads to return.

    Returns:
        Dict with keys: ``status``, ``leads`` (list of lead dicts with
        ``id``, ``business_name``, ``website``, ``bucket``, ``email``).
    """
    from database.lead_repo import get_pending_audits as _repo_get

    leads = _repo_get(limit)
    return {"status": "success", "leads": leads}


def save_audit_result(lead_id: str, audit_data: str) -> dict[str, Any]:
    """Persist an audit result to the database.

    Args:
        lead_id: The MongoDB ObjectId of the lead.
        audit_data: JSON string containing the full audit result (score,
            issues, qualified flag, etc.).

    Returns:
        Dict with keys: ``status``, ``message``.
    """
    from database.lead_repo import save_audits_batch

    data = json.loads(audit_data) if isinstance(audit_data, str) else audit_data
    save_audits_batch([{"lead_id": lead_id, "data": data}])
    return {"status": "success", "message": f"Audit saved for lead {lead_id}"}


def get_qualified_leads(limit: int = 20) -> dict[str, Any]:
    """Fetch leads that passed the audit qualification threshold.

    Args:
        limit: Maximum number of leads to return.

    Returns:
        Dict with keys: ``status``, ``leads`` (list of lead dicts with
        audit results attached).
    """
    from database.lead_repo import get_qualified_leads as _repo_get

    leads = _repo_get(limit)
    return {"status": "success", "leads": leads}


def discover_leads(limit: int = 20) -> dict[str, Any]:
    """Run lead discovery pipeline and return newly discovered leads.

    Args:
        limit: Maximum number of search queries to execute.

    Returns:
        Dict with keys: ``status``, ``queries_executed``, ``leads_found``,
        ``leads_saved``.
    """
    from discovery.engine import PlaywrightScraper

    scraper = PlaywrightScraper()
    result = scraper.run(max_queries=limit)
    return {
        "status": "success",
        "queries_executed": result["queries_executed"],
        "leads_found": result["leads_found"],
        "leads_saved": result["leads_saved"],
    }
