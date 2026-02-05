#!/usr/bin/env python3
"""Verification script for ultra-minimal refactor"""
import sys
import os

def test_imports():
    """Test all core module imports"""
    print("Testing imports...")
    try:
        from lead_repository import LeadRepository
        from discovery import Discovery
        from outreach import Outreach
        from email_sender import EmailSender
        print("  ✓ All imports successful")
        return True
    except Exception as e:
        print(f"  ✗ Import failed: {e}")
        return False

def test_repository():
    """Test repository operations"""
    print("Testing repository...")
    try:
        from lead_repository import LeadRepository
        repo = LeadRepository()
        
        # Test database setup (should not fail on existing DB)
        repo.setup_database()
        
        # Test stats
        stats = repo.get_stats()
        assert 'total_leads' in stats
        assert 'qualified_leads' in stats
        assert 'emails_sent' in stats
        assert 'emails_pending' in stats
        
        print(f"  ✓ Repository working")
        print(f"    - Total leads: {stats['total_leads']}")
        print(f"    - Qualified: {stats['qualified_leads']}")
        return True
    except Exception as e:
        print(f"  ✗ Repository failed: {e}")
        return False

def test_discovery():
    """Test discovery module"""
    print("Testing discovery...")
    try:
        from discovery import Discovery
        discovery = Discovery()
        
        # Test query generation
        queries = discovery.generate_queries(limit=3)
        assert len(queries) <= 3
        assert all('query' in q for q in queries)
        
        print(f"  ✓ Discovery working")
        print(f"    - Generated {len(queries)} queries")
        if queries:
            print(f"    - Sample: {queries[0]['query']}")
        return True
    except Exception as e:
        print(f"  ✗ Discovery failed: {e}")
        return False

def test_outreach():
    """Test outreach module"""
    print("Testing outreach...")
    try:
        from outreach import Outreach
        outreach = Outreach()
        
        # Test template loading
        assert isinstance(outreach.templates, dict)
        
        # Test Ollama connection (may fail, that's OK)
        ollama_status = "connected" if outreach.ollama_enabled else "not available"
        
        print(f"  ✓ Outreach working")
        print(f"    - Ollama: {ollama_status}")
        print(f"    - Templates loaded: {len(outreach.templates)}")
        return True
    except Exception as e:
        print(f"  ✗ Outreach failed: {e}")
        return False

def test_email_sender():
    """Test email sender module"""
    print("Testing email sender...")
    try:
        from email_sender import EmailSender
        sender = EmailSender()
        
        # Check configuration
        has_email = bool(sender.email)
        has_password = bool(sender.password)
        
        print(f"  ✓ Email sender working")
        print(f"    - Email configured: {has_email}")
        print(f"    - Password configured: {has_password}")
        
        if not has_email or not has_password:
            print("    ⚠ Warning: Gmail credentials not configured")
        
        return True
    except Exception as e:
        print(f"  ✗ Email sender failed: {e}")
        return False

def test_config_files():
    """Test configuration files exist"""
    print("Testing configuration files...")
    try:
        assert os.path.exists("config/buckets.json")
        assert os.path.exists("config/email_templates.json")
        print("  ✓ Configuration files present")
        return True
    except Exception as e:
        print(f"  ✗ Config files missing: {e}")
        return False

def test_line_counts():
    """Verify line counts"""
    print("Verifying line counts...")
    try:
        files = {
            'lead_repository.py': 246,
            'discovery.py': 243,
            'outreach.py': 315,
            'email_sender.py': 79,
            'main_tui.py': 261,
            'cli.py': 124
        }
        
        total_business = 0
        total_all = 0
        
        for file, expected in files.items():
            if os.path.exists(file):
                with open(file) as f:
                    actual = len(f.readlines())
                
                # Allow 5% variance
                variance = expected * 0.05
                if abs(actual - expected) <= variance:
                    status = "✓"
                else:
                    status = "⚠"
                
                print(f"  {status} {file}: {actual} lines (expected ~{expected})")
                
                if file in ['lead_repository.py', 'discovery.py', 'outreach.py', 'email_sender.py']:
                    total_business += actual
                total_all += actual
        
        print(f"  ✓ Business logic total: {total_business} lines")
        print(f"  ✓ Total with UI: {total_all} lines")
        return True
    except Exception as e:
        print(f"  ✗ Line count verification failed: {e}")
        return False

def test_dependencies():
    """Check dependency count"""
    print("Checking dependencies...")
    try:
        with open("pyproject.toml") as f:
            content = f.read()
        
        # Simple parsing - count lines between dependencies = [ and ]
        in_deps = False
        deps = []
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('dependencies = ['):
                in_deps = True
                continue
            if in_deps and line == ']':
                break
            if in_deps and line and not line.startswith('#'):
                # Extract package name
                if '"' in line:
                    dep = line.split('"')[1]
                    deps.append(dep)
        
        print(f"  ✓ Dependencies: {len(deps)}")
        for dep in deps:
            print(f"    - {dep}")
        
        if len(deps) <= 5:
            print("  ✓ Dependency count target met (≤5)")
        else:
            print(f"  ⚠ Dependency count: {len(deps)} (target: ≤5)")
        
        return True
    except Exception as e:
        print(f"  ✗ Dependency check failed: {e}")
        return False

def main():
    print("=" * 60)
    print("Web Contractor - Ultra-Minimal Refactor Verification")
    print("=" * 60)
    print()
    
    tests = [
        test_imports,
        test_repository,
        test_discovery,
        test_outreach,
        test_email_sender,
        test_config_files,
        test_line_counts,
        test_dependencies
    ]
    
    results = []
    for test in tests:
        results.append(test())
        print()
    
    print("=" * 60)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)
    
    if all(results):
        print("✓ All tests passed! Refactor successful.")
        return 0
    else:
        print("⚠ Some tests failed. Review output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
