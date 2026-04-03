"""
Double-click this file to launch Claude Usage Monitor (no console window).
This file must be in the same directory as claude_usage.py.
"""
import os
import runpy

script_dir = os.path.dirname(os.path.abspath(__file__))
runpy.run_path(os.path.join(script_dir, "claude_usage.py"), run_name="__main__")
