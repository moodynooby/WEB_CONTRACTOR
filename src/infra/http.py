"""HTTP utilities — website fetching and parsing."""

from typing import Any

from infra.logging import get_logger

logger = get_logger(__name__)


def fetch_website(url: str) -> dict[str, Any]:
    """Fetch a website URL and return parsed HTML content.

    Args:
        url: The website URL to fetch (must include http/https scheme).

    Returns:
        Dict with keys: ``status`` (``success``/``error``), ``html`` (raw HTML
        string), ``soup_text`` (extracted text content), ``status_code`` (int),
        and ``error`` (error message on failure).
    """
    import requests
    from bs4 import BeautifulSoup

    if not url.startswith("http"):
        url = f"https://{url}"

    resp = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (WebContractor ADK Audit)"},
        timeout=15,
    )
    if resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return {
            "status": "success",
            "html": resp.text[:50000],
            "soup_text": text[:10000],
            "status_code": resp.status_code,
        }
    return {
        "status": "error",
        "error": f"HTTP {resp.status_code}",
        "status_code": resp.status_code,
    }
