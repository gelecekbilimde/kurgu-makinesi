#!/usr/bin/env python3
"""
Kurgu Makinesi - Rough Cutting Tool for Video Editors

A CLI tool to help video editors create rough cuts from scripts.
Supports Kdenlive and Shotcut workflows.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from shared.script_parser import Script, find_script_files
from shared.kdenlive import KdenliveProject
from shared.shotcut import ShotcutProject


def main():
    """Main CLI entry point."""
    # Handle --help flag
    if len(sys.argv) >= 2 and sys.argv[1] in ["--help", "-h"]:
        print("Kurgu Makinesi - Rough Cutting Tool for Video Editors")
        print("")
        print("Usage: kurgu_makinesi.py <command> [args]")
        print("")
        print("Commands:")
        print("  import <script_path>     Import a script and create project")
        print("  list                     List available scripts")
        print("  help                     Show this help message")
        return 0
    
    if len(sys.argv) < 2:
        print("Kurgu Makinesi - Rough Cutting Tool for Video Editors")
        print("")
        print("Usage: kurgu_makinesi.py <command> [args]")
        print("")
        print("Commands:")
        print("  import <script_path>     Import a script and create project")
        print("  list                     List available scripts")
        print("  help                     Show this help message")
        return 0
    
    command = sys.argv[1]
    
    if command == "help":
        main()
        return 0
    elif command == "list":
        scripts = find_script_files(".")
        for script_path in scripts:
            print(f"  {script_path}")
        return 0
    elif command == "import":
        if len(sys.argv) < 3:
            print("Error: Please provide a script path")
            return 1
        
        script_path = sys.argv[2]
        project_type = sys.argv[3] if len(sys.argv) > 3 else "kdenlive"
        
        try:
            script = Script(script_path)
            script.load(script_path)
            print(f"Loaded: {script}")
            
            if project_type == "kdenlive":
                project = KdenliveProject()
            else:
                project = ShotcutProject()
            
            project.import_script(script)
            print("Project created successfully!")
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    else:
        print(f"Unknown command: {command}")
        print("")
        main()
        return 0


if __name__ == "__main__":
    sys.exit(main())
