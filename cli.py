#!/usr/bin/env python3
"""Web Contractor - Simple CLI Interface"""
import argparse
import sys
from discovery import Discovery
from outreach import Outreach
from email_sender import EmailSender
from lead_repository import LeadRepository


def cmd_discovery(args):
    """Run discovery pipeline"""
    discovery = Discovery()
    result = discovery.run(bucket_name=args.bucket, max_queries=args.queries)
    print(f"\n✓ Discovery Complete")
    print(f"  Queries: {result['queries_executed']}")
    print(f"  Found: {result['leads_found']}")
    print(f"  Saved: {result['leads_saved']}")


def cmd_audit(args):
    """Run audit pipeline"""
    outreach = Outreach()
    result = outreach.audit_leads(limit=args.limit)
    print(f"\n✓ Audit Complete")
    print(f"  Audited: {result['audited']}")
    print(f"  Qualified: {result['qualified']}")


def cmd_generate(args):
    """Generate emails"""
    outreach = Outreach()
    result = outreach.generate_emails(limit=args.limit)
    print(f"\n✓ Email Generation Complete")
    print(f"  Generated: {result['generated']}")


def cmd_send(args):
    """Send emails"""
    sender = EmailSender()
    result = sender.send_pending_emails(limit=args.limit)
    print(f"\n✓ Email Sending Complete")
    print(f"  Sent: {result['sent']}")
    print(f"  Failed: {result['failed']}")


def cmd_stats(args):
    """Show statistics"""
    repo = LeadRepository()
    stats = repo.get_stats()
    print(f"\n{'='*40}")
    print("Web Contractor Statistics")
    print(f"{'='*40}")
    print(f"Total Leads:      {stats['total_leads']}")
    print(f"Qualified Leads:  {stats['qualified_leads']}")
    print(f"Emails Sent:      {stats['emails_sent']}")
    print(f"Emails Pending:   {stats['emails_pending']}")
    print(f"{'='*40}\n")


def cmd_init(args):
    """Initialize database"""
    repo = LeadRepository()
    repo.setup_database()
    print("✓ Database initialized")


def main():
    parser = argparse.ArgumentParser(
        description="Web Contractor - Lead Generation & Outreach Automation"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Discovery command
    discovery_parser = subparsers.add_parser("discovery", help="Run discovery pipeline")
    discovery_parser.add_argument(
        "--bucket", type=str, default=None, help="Target specific bucket"
    )
    discovery_parser.add_argument(
        "--queries", type=int, default=5, help="Max queries to execute"
    )
    discovery_parser.set_defaults(func=cmd_discovery)

    # Audit command
    audit_parser = subparsers.add_parser("audit", help="Audit pending leads")
    audit_parser.add_argument(
        "--limit", type=int, default=20, help="Max leads to audit"
    )
    audit_parser.set_defaults(func=cmd_audit)

    # Generate command
    generate_parser = subparsers.add_parser("generate", help="Generate emails")
    generate_parser.add_argument(
        "--limit", type=int, default=20, help="Max emails to generate"
    )
    generate_parser.set_defaults(func=cmd_generate)

    # Send command
    send_parser = subparsers.add_parser("send", help="Send pending emails")
    send_parser.add_argument(
        "--limit", type=int, default=10, help="Max emails to send"
    )
    send_parser.set_defaults(func=cmd_send)

    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show statistics")
    stats_parser.set_defaults(func=cmd_stats)

    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize database")
    init_parser.set_defaults(func=cmd_init)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Execute command
    args.func(args)


if __name__ == "__main__":
    main()
