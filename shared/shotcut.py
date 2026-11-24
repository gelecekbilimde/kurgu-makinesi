#!/usr/bin/env python3
# shared/shotcut.py
"""
Shotcut integration for Kurgu Makinesi.
"""

import subprocess
from pathlib import Path
from typing import Optional, List


class ShotcutProject:
    """Manages a new Shotcut project."""
    
    def __init__(self):
        self.project_path: Optional[Path] = None
        self._cli_name = "shotcut"
    
    def create_new(self, title: str = "Untitled", duration: int = 60) -> "ShotcutProject":
        """Create a new Shotcut project."""
        # Check if shotcut is available
        try:
            subprocess.run(
                ["shotcut", "--version"],
                capture_output=True,
                check=False
            )
        except FileNotFoundError:
            print("  ⚠️  Shotcut not found in PATH")
            return self
        
        # Create project file (SPJ format)
        self.project_path = Path(f"{title}.spj")
        
        # Write minimal SPJ project structure
        spj_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE Project>
<Project version="2">
  <Title>{title}</Title>
  <Duration>{duration}</Duration>
</Project>
"""
        
        self.project_path.write_text(spj_content, encoding="utf-8")
        print(f"  ✓ Created project: {self.project_path}")
        
        return self
    
    def add_clip(self, clip_path: str) -> bool:
        """Add a media clip to the project."""
        if not self.project_path:
            print("  ✗ No active project")
            return False
        
        # In real implementation, would use Shotcut API or CLI
        print(f"  ℹ️  Would add clip: {clip_path}")
        return True
    
    def render(self, output_path: Optional[str] = None) -> bool:
        """Render the project."""
        if not self.project_path:
            print("  ✗ No active project")
            return False
        
        # In real implementation, would use Shotcut CLI or API
        print(f"  ℹ️  Would render to: {output_path}")
        return True
    
    def close(self) -> None:
        """Close the project."""
        if self.project_path and self.project_path.exists():
            self.project_path.unlink()
            print(f"  ✓ Closed project: {self.project_path}")
        else:
            print("  ℹ️  No active project to close")

