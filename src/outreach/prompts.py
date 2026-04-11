"""Shared email prompt building — used by both the legacy EmailGenerator
and the ADK FunctionTools in infra/adk_tools.py.

All prompt templates, bucket angle/CTA injection, and issue formatting
live here so there is a single source of truth.
"""


from infra.settings import get_section


def format_issues(issues: list[dict], top_n: int = 3) -> str:
    """Format audit issues into a bullet list for the email prompt.

    Args:
        issues: List of issue dicts with ``severity`` and ``description``.
        top_n: How many top issues to include.

    Returns:
        Newline-separated bullet list.
    """
    critical = [i for i in issues if i.get("severity") == "critical"]
    warnings = [i for i in issues if i.get("severity") == "warning"]
    top_issues = (critical + warnings)[:top_n]
    return "\n".join([f"- {i['description']}" for i in top_issues])


def build_email_prompt(
    business_name: str,
    bucket: str,
    issues_summary: str,
    url: str = "",
    angle: str = "",
    cta: str = "",
) -> str:
    """Build the LLM prompt for cold email generation.

    Args:
        business_name: Business name.
        bucket: Industry bucket (e.g., ``"Restaurants"``).
        issues_summary: Formatted audit issues bullet list.
        url: Website URL (optional — included in prompt context).
        angle: Marketing angle from bucket template.
        cta: Call-to-action from bucket template.

    Returns:
        Complete prompt string ready for ``llm.generate_with_retry()``.
    """
    email_config = get_section("email_generation")
    template = email_config.get("prompt_template", "")

    prompt = template.format(
        business_name=business_name,
        bucket=bucket,
        url=url,
        issue_summary=issues_summary,
    )
    if angle:
        prompt += f"\n\nAngle: {angle}"
    if cta:
        prompt += f"\nCTA: {cta}"
    return prompt


def get_email_system_message() -> str:
    """Return the system message for email generation."""
    email_config = get_section("email_generation")
    return email_config.get("system_message", "")


def get_bucket_template(bucket: str) -> dict[str, str]:
    """Get bucket-specific angle and CTA template.

    Args:
        bucket: Industry bucket name.

    Returns:
        Dict with ``angle`` and ``cta`` keys (empty strings if not found).
    """
    email_config = get_section("email_generation")
    bucket_templates = email_config.get("bucket_templates", {})
    return bucket_templates.get(bucket, {})


def build_refine_prompt(subject: str, body: str, instructions: str) -> str:
    """Build the LLM prompt for email refinement.

    Args:
        subject: Current email subject.
        body: Current email body.
        instructions: User refinement instructions.

    Returns:
        Prompt string for the refine LLM call.
    """
    return f"""Refine this cold email.

Instructions: {instructions}

Subject: {subject}
Body:
{body}

Return ONLY JSON: {{"subject": "...", "body": "..."}}"""
