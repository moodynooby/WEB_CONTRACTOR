"""Bucket Manager CLI - Unified interface for managing discovery buckets.

Usage:
    python scripts/manage_buckets.py              # Interactive mode
    python scripts/manage_buckets.py --list       # List all buckets
    python scripts/manage_buckets.py --create     # Create bucket non-interactively

Features:
- Create new buckets using AI-powered BucketManager
- List existing buckets with details
- Delete buckets with confirmation
- Database connectivity check before operations
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def check_db_connection() -> bool:
    """Verify MongoDB connectivity before proceeding."""
    from infra.db_health import check_db_connection as _check

    return _check(PROJECT_ROOT)


def prompt(question: str, default: str = "") -> str:
    """Prompt user for input with optional default."""
    prompt_text = f"  {question} [{default}]: " if default else f"  {question}: "
    try:
        answer = input(prompt_text).strip()
        return answer if answer else default
    except (EOFError, KeyboardInterrupt):
        print("\n\n⚠️  Operation cancelled.")
        sys.exit(1)


def list_buckets():
    """List all existing buckets with details."""
    from database.repository import BucketManager

    print("\n" + "=" * 70)
    print("  📦 Existing Buckets")
    print("=" * 70)

    buckets = BucketManager.list()

    if not buckets:
        print("\n  No buckets found. Use 'create' to add a new bucket.")
        return

    print(f"\n  Found {len(buckets)} bucket(s):\n")

    for i, bucket in enumerate(buckets, 1):
        print(f"  {i}. {bucket['name']}")
        print(f"     Priority: {bucket.get('priority', 'N/A')}")
        print(f"     Categories: {len(bucket.get('categories', []))}")
        print(f"     Max Queries: {bucket.get('max_queries', 'N/A')}")
        print(f"     Max Results: {bucket.get('max_results', 'N/A')}")
        print(f"     Monthly Target: {bucket.get('monthly_target', 'N/A')}")
        print()


def _do_create(business_type: str, locations: list[str], max_queries: int, max_results: int):
    """Shared create logic used by both interactive and non-interactive modes."""
    from database.repository import BucketManager

    print(f"\n[→] Creating bucket for '{business_type}' in {len(locations)} locations...")

    success, message = BucketManager.create(
        business_type=business_type,
        target_locations=locations,
        max_queries=max_queries,
        max_results=max_results,
    )

    print(f"  {'✓' if success else '✗'} {message}")
    return success


def create_bucket_interactive():
    """Interactive wizard to create a new bucket using AI."""
    print("\n" + "=" * 70)
    print("  ✨ Create New Bucket (AI-Powered)")
    print("=" * 70)
    print()
    print("  This wizard uses AI to generate an optimized bucket configuration")
    print("  for your business type and target locations.\n")

    business_type = prompt("Business type (e.g., 'dentists', 'yoga studios')")
    if not business_type:
        print("  ✗ Business type is required")
        return

    locations_str = prompt(
        "Target locations (comma-separated, e.g., 'New York, Los Angeles, Chicago')"
    )
    if not locations_str:
        print("  ✗ At least one location is required")
        return

    target_locations = [loc.strip() for loc in locations_str.split(",") if loc.strip()]

    max_queries = int(prompt("Max queries per run", "10"))
    max_results = int(prompt("Max results per query", "50"))

    success = _do_create(business_type, target_locations, max_queries, max_results)

    if success:
        from database.repository import BucketManager

        config = BucketManager.get_by_name(
            business_type.lower().replace(" ", "_").replace("-", "_")
        )
        if config:
            print("\n  Generated configuration:")
            print(f"    Categories: {len(config.get('categories', []))}")
            print(f"    Search Patterns: {len(config.get('search_patterns', []))}")
            print(f"    Geographic Segments: {len(config.get('geographic_segments', []))}")
            print(f"    Priority: {config.get('priority', 'N/A')}")


def create_bucket_non_interactive(
    business_type: str, locations: str, max_queries: int, max_results: int
):
    """Create bucket without interaction (for scripting/automation)."""
    target_locations = [loc.strip() for loc in locations.split(",") if loc.strip()]
    _do_create(business_type, target_locations, max_queries, max_results)


def delete_bucket():
    """Delete a bucket with confirmation."""
    from database.repository import BucketManager

    print("\n" + "=" * 70)
    print("  🗑️  Delete Bucket")
    print("=" * 70)

    buckets = BucketManager.list()

    if not buckets:
        print("\n  No buckets to delete")
        return

    print("\n  Available buckets:")
    for i, bucket in enumerate(buckets, 1):
        print(f"    {i}. {bucket['name']}")

    print()
    choice = prompt("Enter bucket number to delete (or 'cancel')")

    if choice.lower() in ["cancel", "c", ""]:
        print("  ⚠️  Deletion cancelled")
        return

    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(buckets):
            print("  ✗ Invalid bucket number")
            return

        bucket = buckets[idx]
        confirm = prompt(
            f"Delete bucket '{bucket['name']}' and all related data? (y/N)", "n"
        )
        if confirm.lower() not in ["y", "yes"]:
            print("  ⚠️  Deletion cancelled")
            return

        success, message = BucketManager.delete(bucket["id"], cascade=True)
        print(f"  {'✓' if success else '✗'} {message}")

    except ValueError:
        print("  ✗ Invalid input. Please enter a number.")


def show_menu():
    """Show interactive menu."""
    print("\n" + "=" * 70)
    print("  🏗️  Web Contractor - Bucket Manager")
    print("=" * 70)
    print()
    print("  Available actions:")
    print("    1. List buckets")
    print("    2. Create new bucket (interactive)")
    print("    3. Delete bucket")
    print("    4. Exit")
    print()

    while True:
        choice = prompt("Select action (1-4)", "1")

        if choice in ["1", "list"]:
            list_buckets()
        elif choice in ["2", "create"]:
            create_bucket_interactive()
        elif choice in ["3", "delete"]:
            delete_bucket()
        elif choice in ["4", "exit", "quit", "q", ""]:
            print("\n  👋 Goodbye!")
            return
        else:
            print("  ✗ Invalid choice. Please enter 1-4.")


def main():
    """Main entry point for bucket manager CLI."""
    parser = argparse.ArgumentParser(description="Web Contractor - Bucket Manager CLI")
    parser.add_argument("--list", action="store_true", help="List all buckets")
    parser.add_argument(
        "--create", action="store_true", help="Create bucket non-interactively"
    )
    parser.add_argument(
        "--business-type", type=str, help="Business type (with --create)"
    )
    parser.add_argument(
        "--locations", type=str, help="Comma-separated locations (with --create)"
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        default=10,
        help="Max queries per run (with --create)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=50,
        help="Max results per query (with --create)",
    )

    args = parser.parse_args()

    if not check_db_connection():
        print("\n[✗] Database connectivity check failed. Cannot proceed.")
        sys.exit(1)

    print()

    if args.list:
        list_buckets()
        return

    if args.create:
        if not args.business_type or not args.locations:
            print("✗ --business-type and --locations are required with --create")
            parser.print_help()
            sys.exit(1)

        create_bucket_non_interactive(
            business_type=args.business_type,
            locations=args.locations,
            max_queries=args.max_queries,
            max_results=args.max_results,
        )
        return

    show_menu()


if __name__ == "__main__":
    main()
