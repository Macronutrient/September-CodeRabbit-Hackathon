#!/usr/bin/env python3
"""
Craigslist Post Helper - Entry point script.

This script provides the same interface as before but now uses a modular,
maintainable codebase organized in the src/ directory.
"""

import asyncio
from src.main import main

print("Starting script...")

if __name__ == "__main__":
    asyncio.run(main())
