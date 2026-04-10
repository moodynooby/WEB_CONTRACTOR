"""Bucket Manager CLI - Interactive wizard for managing discovery buckets.

Usage:
    python scripts/manage_buckets.py          # Interactive mode
    python scripts/manage_buckets.py --list   # List all buckets
    python scripts/manage_buckets.py --create # Create bucket non-interactively

Features:
- Create new buckets using AI-powered BucketConfigGenerator
- List existing buckets with details
- Delete buckets with confirmation
- Database connectivity check before operations
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def check_db_connection() -> bool:
    """Verify MongoDB connectivity before proceeding.

    Returns:
        True if database is reachable, False otherwise.
    """
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    mongo_uri = os.getenv("MONGODB_URI")

    if not mongo_uri:
        print("[✗] MONGODB_URI not set in .env file")
        print("[→] Configure MongoDB connection:")
        print(
            "    1. Get a free MongoDB Atlas cluster at: https://www.mongodb.com/atlas"
        )
        print("    2. Add MONGODB_URI to your .env file")
        print("")
        print("[→] Or run the setup wizard: python scripts/setup.py")
        return False

    print("[→] Testing MongoDB connection...")

    try:
        from pymongo import MongoClient

        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        client.close()

        print("[✓] MongoDB connection successful")
        return True

    except ImportError:
        print("[✗] pymongo not installed. Run: uv sync")
        return False
    except Exception as e:
        print(f"[✗] MongoDB connection failed: {e}")
        print("")
        print("[→] Troubleshooting:")
        print("    • Check your MONGODB_URI in .env file")
        print("    • Ensure your IP is whitelisted in MongoDB Atlas")
        return False


def prompt(question: str, default: str = "") -> str:
    """Prompt user for input with optional default.

    Args:
        question: The question to ask
        default: Default value if user presses Enter

    Returns:
        User's input or default value
    """
    if default:
        prompt_text = f"  {question} [{default}]: "
    else:
        prompt_text = f"  {question}: "

    try:
        answer = input(prompt_text).strip()
        return answer if answer else default
    except (EOFError, KeyboardInterrupt):
        print("\n\n⚠️  Operation cancelled.")
        sys.exit(1)


def list_buckets():
    """List all existing buckets with details."""
    from database.repository import get_all_buckets

    print("\n" + "=" * 70)
    print("  📦 Existing Buckets")
    print("=" * 70)

    buckets = get_all_buckets()

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


def create_bucket_interactive():
    """Interactive wizard to create a new bucket using AI."""
    from discovery.engine import BucketConfigGenerator

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
    if not target_locations:
        print("  ✗ At least one valid location is required")
        return

    max_queries_str = prompt("Max queries per run", "10")
    max_results_str = prompt("Max results per query", "50")

    try:
        max_queries = int(max_queries_str)
        max_results = int(max_results_str)
    except ValueError:
        print("  ✗ Invalid number format")
        return

    print("\n[→] Generating bucket configuration with AI...")

    generator = BucketConfigGenerator()

    try:
        config = generator.generate(
            business_type=business_type,
            target_locations=target_locations,
            max_queries=max_queries,
            max_results=max_results,
        )

        is_valid, errors = generator.validate_config(config)

        if not is_valid:
            print("\n  ✗ Configuration validation failed:")
            for error in errors:
                print(f"    - {error}")
            return

        print("\n[✓] Generated configuration:")
        print(f"    Name: {config['name']}")
        print(f"    Categories: {len(config.get('categories', []))}")
        print(f"    Search Patterns: {len(config.get('search_patterns', []))}")
        print(f"    Geographic Segments: {len(config.get('geographic_segments', []))}")
        print(f"    Priority: {config.get('priority', 'N/A')}")

        save = prompt("\nSave this bucket to database?", "y")
        if save.lower() not in ["y", "yes"]:
            print("  ⚠️  Bucket not saved")
            return

        success, message = generator.save_config(config)

        if success:
            print(f"\n  ✓ {message}")
        else:
            print(f"\n  ✗ {message}")

    except Exception as e:
        print(f"\n  ✗ Generation failed: {e}")
        print("  💡 Check your Groq API key in .env file")


def create_bucket_non_interactive(
    business_type: str, locations: str, max_queries: int, max_results: int
):
    """Create bucket without interaction (for scripting/automation).

    Args:
        business_type: Type of business
        locations: Comma-separated locations
        max_queries: Max queries per run
        max_results: Max results per query
    """
    from discovery.engine import BucketConfigGenerator

    target_locations = [loc.strip() for loc in locations.split(",") if loc.strip()]

    if not business_type:
        print("✗ Business type is required (--business-type)")
        sys.exit(1)

    if not target_locations:
        print("✗ At least one location is required (--locations)")
        sys.exit(1)

    print(
        f"[→] Creating bucket for '{business_type}' in {len(target_locations)} locations..."
    )

    generator = BucketConfigGenerator()

    try:
        config = generator.generate(
            business_type=business_type,
            target_locations=target_locations,
            max_queries=max_queries,
            max_results=max_results,
        )

        is_valid, errors = generator.validate_config(config)

        if not is_valid:
            print("✗ Configuration validation failed:")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)

        success, message = generator.save_config(config)

        if success:
            print(f"✓ {message}")
        else:
            print(f"✗ {message}")
            sys.exit(1)

    except Exception as e:
        print(f"✗ Generation failed: {e}")
        sys.exit(1)


def delete_bucket():
    """Delete a bucket with confirmation."""
    from database.repository import get_all_buckets, delete_bucket

    print("\n" + "=" * 70)
    print("  🗑️  Delete Bucket")
    print("=" * 70)

    buckets = get_all_buckets()

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
        bucket_name = bucket["name"]

        confirm = prompt(
            f"Delete bucket '{bucket_name}' and all related data? (y/N)", "n"
        )
        if confirm.lower() not in ["y", "yes"]:
            print("  ⚠️  Deletion cancelled")
            return

        success, message = delete_bucket(bucket["id"], cascade=True)

        if success:
            print(f"  ✓ {message}")
        else:
            print(f"  ✗ {message}")

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
