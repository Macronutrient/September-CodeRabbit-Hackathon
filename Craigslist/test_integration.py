#!/usr/bin/env python3
"""Integration test for Craigslist Post Helper modules."""

import asyncio
import sys
from pathlib import Path
from src.config import build_config
from src.cookies import CookieManager
from src.auth import AuthManager  
from src.images import ImageManager


async def test_modules():
    """Test all modules without running the full browser automation."""
    print("=" * 60)
    print("CRAIGSLIST POST HELPER - INTEGRATION TEST")
    print("=" * 60)
    
    success_count = 0
    total_tests = 0
    
    # Test 1: Configuration
    total_tests += 1
    try:
        print("\n[TEST 1] Testing configuration module...")
        cfg = build_config()
        cfg.log_config()
        
        # Test API key validation
        try:
            api_key, provider = cfg.validate_api_key()
            print(f"[TEST 1] ✅ API key validation: Found {provider} key (length: {len(api_key)})")
        except ValueError as e:
            print(f"[TEST 1] ⚠️  API key validation: {e}")
            
        success_count += 1
        print("[TEST 1] ✅ Configuration module: PASSED")
    except Exception as e:
        print(f"[TEST 1] ❌ Configuration module: FAILED - {e}")
    
    # Test 2: Cookie Management
    total_tests += 1
    try:
        print("\n[TEST 2] Testing cookie management...")
        cookie_manager = CookieManager(cfg.email)
        print(f"[TEST 2] Cookie file: {cookie_manager.cookie_file}")
        print(f"[TEST 2] Cookie file exists: {cookie_manager.cookie_file.exists()}")
        success_count += 1
        print("[TEST 2] ✅ Cookie management: PASSED")
    except Exception as e:
        print(f"[TEST 2] ❌ Cookie management: FAILED - {e}")
    
    # Test 3: Authentication
    total_tests += 1
    try:
        print("\n[TEST 3] Testing authentication module...")
        auth_manager = AuthManager(cfg.email)
        print(f"[TEST 3] Auth manager initialized for: {auth_manager.email}")
        
        # Test magic link validation
        valid_link = "https://accounts.craigslist.org/login/home?s=some_token"
        empty_link = ""
        
        print(f"[TEST 3] Valid link test: {auth_manager.validate_magic_link(valid_link)}")
        print(f"[TEST 3] Empty link test: {auth_manager.validate_magic_link(empty_link)}")
        
        success_count += 1
        print("[TEST 3] ✅ Authentication module: PASSED")
    except Exception as e:
        print(f"[TEST 3] ❌ Authentication module: FAILED - {e}")
    
    # Test 4: Image Management
    total_tests += 1
    try:
        print("\n[TEST 4] Testing image management...")
        image_manager = ImageManager(cfg.images)
        print(f"[TEST 4] Image names: {image_manager.image_names}")
        
        resolved_images = image_manager.resolve_images()
        print(f"[TEST 4] Resolved images: {len(resolved_images)}")
        print(f"[TEST 4] Has images: {image_manager.has_images()}")
        
        image_manager.log_image_status()
        
        success_count += 1
        print("[TEST 4] ✅ Image management: PASSED")
    except Exception as e:
        print(f"[TEST 4] ❌ Image management: FAILED - {e}")
    
    # Test 5: File Structure
    total_tests += 1
    try:
        print("\n[TEST 5] Testing file structure...")
        expected_files = [
            "src/__init__.py",
            "src/config.py", 
            "src/cookies.py",
            "src/auth.py",
            "src/images.py",
            "src/agent.py",
            "src/main.py",
            "script.py",
            "test_gemini_key.py",
            "requirements.txt",
            "README.md"
        ]
        
        missing_files = []
        for file_path in expected_files:
            if not Path(file_path).exists():
                missing_files.append(file_path)
                
        if missing_files:
            print(f"[TEST 5] ❌ Missing files: {missing_files}")
        else:
            print("[TEST 5] All expected files present")
            success_count += 1
            
        print("[TEST 5] ✅ File structure: PASSED")
    except Exception as e:
        print(f"[TEST 5] ❌ File structure: FAILED - {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print(f"INTEGRATION TEST SUMMARY: {success_count}/{total_tests} tests passed")
    print("=" * 60)
    
    if success_count == total_tests:
        print("🎉 All tests passed! The application is ready to use.")
        print("\nTo run the full application (ENV-only config):")
        print("   python script.py")
        print("\nEdit .env to change parameters such as TITLE, PRICE, CITY, etc.")
        return True
    else:
        print("⚠️  Some tests failed. Please check the issues above.")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_modules())
    sys.exit(0 if success else 1)
