"""Web Contractor — single entry point for environment initialization.

All modules import from here to ensure dotenv is loaded before any
configuration or secrets are accessed.
"""

from dotenv import load_dotenv

load_dotenv()
