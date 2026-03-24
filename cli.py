"""Web Contractor - CLI Entry Points

Provides headless CLI commands for discovery and audit operations.
"""

import click
from dotenv import load_dotenv

load_dotenv()

from core.discovery import PlaywrightScraper  # noqa: E402
from core.audit import AuditOrchestrator  # noqa: E402


@click.group()
def cli():
    """Web Contractor - Headless CLI for lead discovery and auditing."""
    pass


@cli.command()
@click.option(
    "--bucket",
    "-b",
    default=None,
    help="Specific bucket name to process (default: all buckets)",
)
@click.option(
    "--max-queries",
    "-q",
    default=None,
    type=int,
    help="Maximum queries to run (overrides config)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Enable verbose output",
)
def discover(bucket: str | None, max_queries: int | None, verbose: bool):
    """Run lead discovery - generate queries and scrape leads.
    
    Executes the full discovery pipeline:
    1. Generate search queries from bucket patterns
    2. Scrape leads from enabled sources
    3. Save leads to database
    """
    def logger(message: str, style: str = "") -> None:
        """Simple logger for CLI output."""
        if verbose or style in ("info", "success", "error", "warning"):
            prefix = ""
            if style == "error":
                prefix = "❌ "
            elif style == "success":
                prefix = "✅ "
            elif style == "warning":
                prefix = "⚠️ "
            elif style == "info":
                prefix = "ℹ️ "
            click.echo(f"{prefix}{message}")

    scraper = PlaywrightScraper(logger=logger)
    result = scraper.run(bucket_name=bucket, max_queries=max_queries)
    
    click.echo("\n" + "=" * 60)
    click.echo("DISCOVERY SUMMARY")
    click.echo("=" * 60)
    click.echo(f"Queries executed: {result['queries_executed']}")
    click.echo(f"Leads found: {result['leads_found']}")
    click.echo(f"Leads saved: {result['leads_saved']}")
    click.echo("=" * 60)


@cli.command()
@click.option(
    "--limit",
    "-l",
    default=20,
    type=int,
    help="Maximum leads to audit (default: 20)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Enable verbose output",
)
def audit(limit: int, verbose: bool):
    """Run audit on pending leads.
    
    Audits leads that haven't been processed yet:
    1. Fetch website content
    2. Run multi-agent audit pipeline (Content, Business, Technical, Performance)
    3. Score and qualify leads
    4. Save audit results to database
    """
    def logger(message: str, style: str = "") -> None:
        """Simple logger for CLI output."""
        if verbose or style in ("info", "success", "error", "warning"):
            prefix = ""
            if style == "error":
                prefix = "❌ "
            elif style == "success":
                prefix = "✅ "
            elif style == "warning":
                prefix = "⚠️ "
            elif style == "info":
                prefix = "ℹ️ "
            click.echo(f"{prefix}{message}")

    orchestrator = AuditOrchestrator(logger=logger)
    result = orchestrator.run(limit=limit)
    
    click.echo("\n" + "=" * 60)
    click.echo("AUDIT SUMMARY")
    click.echo("=" * 60)
    click.echo(f"Leads audited: {result['audited']}")
    click.echo(f"Leads qualified: {result['qualified']}")
    click.echo("=" * 60)


@cli.command()
def tui():
    """Launch the Textual TUI interface.
    
    Opens the interactive terminal UI for managing leads,
    discovery, and audit operations.
    """
    from ui.app import WebContractorTUI
    
    app = WebContractorTUI()
    app.run()


def main():
    """Main entry point for CLI."""
    cli()


if __name__ == "__main__":
    main()
