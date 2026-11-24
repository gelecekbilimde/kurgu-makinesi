#!/usr/bin/env python3
"""
Test script for Kurgu Makinesi rough cutting tool.

Run with: python3 test_kurgu.py [script_path]
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from shared.script_parser import Script


def test_script_parsing():
    """Test basic script parsing."""
    print("Testing script parser...")
    
    # Create a sample script with tags at start of lines (as the parser expects)
    sample_script = """## CHAPTER 1: Introduction
#intro
Welcome to this tutorial.

## CHAPTER 2: Main Content
#main
Here's how it works...

## CHAPTER 3: Conclusion
#outro
That wraps up the basics.
    """
    
    # Write sample script
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(sample_script)
        temp_path = f.name
    
    try:
        # Load and parse
        script = Script(temp_path)
        script.load(temp_path)
        
        print(f"  ✓ Loaded: {script}")
        print(f"  - Chapters: {len(script.chapters)}")
        print(f"  - Tags: {len(script.tags)}")
        
        # Verify
        assert len(script.chapters) == 3, "Expected 3 chapters"
        assert len(script.tags) >= 1, "Expected at least 1 tag"
        
        print("  ✓ All assertions passed!")
        return True
    finally:
        import os
        os.unlink(temp_path)


def test_kdenlive_import():
    """Test Kdenlive project creation."""
    print("\nTesting Kdenlive integration...")
    
    from shared.kdenlive import KdenliveProject
    
    project = KdenliveProject()
    project.create_new()
    
    print(f"  ✓ Project created")
    return True


def test_shotcut_import():
    """Test Shotcut project creation."""
    print("\nTesting Shotcut integration...")
    
    from shared.shotcut import ShotcutProject
    
    project = ShotcutProject()
    project.create_new()
    
    print(f"  ✓ Project created")
    return True


def test_cli():
    """Test CLI help output."""
    print("\nTesting CLI...")
    
    import subprocess
    result = subprocess.run(
        [sys.executable, 'kurgu_makinesi.py', '--help'],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0 and 'Rough Cutting Tool' in result.stdout:
        print(f"  ✓ CLI help works")
        return True
    else:
        print(f"  ✗ CLI help failed: {result.stderr}")
        return False


def main():
    """Run all tests."""
    print("=" * 50)
    print("Kurgu Makinesi - Test Suite")
    print("=" * 50)
    
    results = []
    
    # Run tests
    results.append(("Script Parser", test_script_parsing()))
    results.append(("Kdenlive Import", test_kdenlive_import()))
    results.append(("Shotcut Import", test_shotcut_import()))
    results.append(("CLI", test_cli()))
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Results")
    print("=" * 50)
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
    
    total_passed = sum(1 for _, p in results if p)
    print(f"\n{total_passed}/{len(results)} tests passed")
    
    return 0 if all(p for _, p in results) else 1


if __name__ == '__main__':
    sys.exit(main())
