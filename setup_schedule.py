#!/usr/bin/env python3
"""
Setup a macOS launchd schedule for the Medium Daily Digest Agent.
Creates a LaunchAgent plist that runs the digest daily at 7:00 AM.

Usage:
    python setup_schedule.py            # Install the schedule
    python setup_schedule.py --remove   # Remove the schedule
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

PLIST_NAME = "com.judge.medium-digest-agent"
PLIST_DIR = Path.home() / "Library" / "LaunchAgents"


def get_plist_content(project_dir: Path, python_path: str) -> str:
    """Generate the launchd plist XML content."""
    log_dir = Path.home() / "medium-digests" / "logs"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_NAME}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{project_dir / 'main.py'}</string>
    </array>

    <key>WorkingDirectory</key>
    <string>{project_dir}</string>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>7</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>EnvironmentVariables</key>
    <dict>
        <key>ANTHROPIC_API_KEY</key>
        <string>{os.environ.get('ANTHROPIC_API_KEY', 'YOUR_API_KEY_HERE')}</string>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>

    <key>StandardOutPath</key>
    <string>{log_dir / 'digest-stdout.log'}</string>
    <key>StandardErrorPath</key>
    <string>{log_dir / 'digest-stderr.log'}</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""


def install(project_dir: Path):
    """Install the launchd agent."""
    PLIST_DIR.mkdir(parents=True, exist_ok=True)
    log_dir = Path.home() / "medium-digests" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Find python
    python_path = sys.executable
    print(f"📍 Python: {python_path}")
    print(f"📁 Project: {project_dir}")

    plist_path = PLIST_DIR / f"{PLIST_NAME}.plist"
    content = get_plist_content(project_dir, python_path)
    plist_path.write_text(content)
    print(f"📝 Plist written: {plist_path}")

    # Check for API key placeholder
    if "YOUR_API_KEY_HERE" in content:
        print("\n⚠️  WARNING: ANTHROPIC_API_KEY not found in environment!")
        print("   Edit the plist file and replace YOUR_API_KEY_HERE with your key:")
        print(f"   nano {plist_path}\n")

    # Load the agent
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)
    print(f"✅ Agent loaded! Will run daily at 7:00 AM.")
    print(f"   Digests saved to: ~/medium-digests/")
    print(f"   Logs saved to:    ~/medium-digests/logs/")
    print(f"\n   To test now: launchctl start {PLIST_NAME}")
    print(f"   To stop:     launchctl unload {plist_path}")


def remove():
    """Remove the launchd agent."""
    plist_path = PLIST_DIR / f"{PLIST_NAME}.plist"
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
        plist_path.unlink()
        print(f"🗑️  Agent removed: {plist_path}")
    else:
        print("ℹ️  No agent found to remove.")


def main():
    parser = argparse.ArgumentParser(description="Setup daily schedule for Medium Digest Agent")
    parser.add_argument("--remove", action="store_true", help="Remove the scheduled agent")
    args = parser.parse_args()

    if args.remove:
        remove()
    else:
        project_dir = Path(__file__).parent.resolve()
        install(project_dir)


if __name__ == "__main__":
    main()
