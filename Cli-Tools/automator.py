"""Web Contractor Automation CLI
Usage:
    python automator.py --list-buckets
    python automator.py --generate [bucket_name]
    python automator.py --consolidate
    python automator.py --migrate-config
"""
import argparse
import json
import sys
import sqlite3
from discovery import Discovery
from lead_repository import LeadRepository

def list_buckets():
    """List buckets from database"""
    print("\n" + "="*50)
    print("AVAILABLE BUCKETS (Database)")
    print("="*50)
    
    repo = LeadRepository()
    buckets = repo.get_all_buckets()
    
    if buckets:
        for i, b in enumerate(buckets, 1):
            print(f"{i}. {b['name']} (Target: {b.get('monthly_target', 'N/A')})")
    else:
        print("No buckets found in database. Run --migrate-config to import from files.")

    print("\n" + "="*50)
    print("DATABASE STATUS (Leads per Bucket)")
    print("="*50)
    
    try:
        conn = repo._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT bucket, COUNT(*) FROM leads GROUP BY bucket ORDER BY COUNT(*) DESC")
        rows = cursor.fetchall()
        
        if not rows:
            print("No leads in database.")
        
        for bucket, count in rows:
            print(f"- {bucket or 'Unknown'}: {count} leads")
            
        conn.close()
    except Exception as e:
        print(f"Error querying database: {e}")
    print("\n")

def generate_leads(bucket_name=None):
    """Run discovery process"""
    print(f"\nStarting generation for bucket: {bucket_name if bucket_name else 'ALL'}")
    discovery = Discovery()
    # If bucket_name is provided, filter for it
    if bucket_name:
        repo = LeadRepository()
        buckets = repo.get_all_buckets()
        valid_names = [b["name"] for b in buckets]
        
        if not valid_names:
             # Fallback to file check if DB is empty
             try:
                with open("config/buckets.json") as f:
                    data = json.load(f)
                    valid_names = [b["name"] for b in data.get("buckets", [])]
             except:
                 pass

        if bucket_name not in valid_names:
            print(f"Error: Bucket '{bucket_name}' not found.")
            print(f"Valid buckets: {', '.join(valid_names)}")
            return

    discovery.run(bucket_name=bucket_name)

def consolidate_db():
    """Consolidate and optimize database"""
    print("\nConsolidating database...")
    repo = LeadRepository()
    result = repo.consolidate_database()
    print(f"Deleted {result['deleted_empty_leads']} empty leads (no contact info).")
    print(f"Database status: {result['status']}")
    print("Consolidation complete.")

def migrate_config():
    """Migrate config from JSON files to Database"""
    print("\nMigrating configuration to database...")
    repo = LeadRepository()
    repo.setup_database() # Ensure tables exist
    
    # 1. Migrate Buckets
    try:
        with open("config/buckets.json") as f:
            data = json.load(f)
            
            # Save global config
            if "geographic_focus" in data:
                repo.save_config("geographic_focus", data["geographic_focus"])
                print("✓ Saved geographic_focus to app_config")

            # Save buckets
            for bucket in data.get("buckets", []):
                repo.save_bucket(bucket)
                print(f"✓ Saved bucket: {bucket['name']}")
                
    except FileNotFoundError:
        print("Warning: config/buckets.json not found.")
    except Exception as e:
        print(f"Error migrating buckets: {e}")

    # 2. Migrate Email Templates
    try:
        with open("config/email_templates.json") as f:
            data = json.load(f)
            templates = data.get("templates", {})
            
            for bucket_name, issues in templates.items():
                for issue_type, tpl in issues.items():
                    repo.save_template(bucket_name, issue_type, tpl)
                    print(f"✓ Saved template: {bucket_name} - {issue_type}")
                    
    except FileNotFoundError:
        print("Warning: config/email_templates.json not found.")
    except Exception as e:
        print(f"Error migrating templates: {e}")

    print("\nMigration complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Web Contractor Automation Tool")
    parser.add_argument("--list-buckets", action="store_true", help="List available buckets and DB stats")
    parser.add_argument("--generate", type=str, nargs="?", const="ALL", help="Generate leads (optional: specify bucket name)")
    parser.add_argument("--consolidate", action="store_true", help="Consolidate and optimize database")
    parser.add_argument("--migrate-config", action="store_true", help="Migrate JSON config to Database")

    args = parser.parse_args()

    if args.list_buckets:
        list_buckets()
    elif args.generate:
        bucket = None if args.generate == "ALL" else args.generate
        generate_leads(bucket)
    elif args.consolidate:
        consolidate_db()
    elif args.migrate_config:
        migrate_config()
    else:
        parser.print_help()
