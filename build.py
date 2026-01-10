import PyInstaller.__main__
import os
import shutil
from pathlib import Path

def build():
    # Define build arguments
    # Note: We are bundling 'app.py' and 'src' into the internal _MEIPASS directory
    # The 'META' folder is explicitly EXCLUDED from the bundle so it can be updated externally
    
    args = [
        'launcher.py',  # Entry point
        '--name=SearchTool',
        '--onefile',
        '--clean',
        
        # Streamlit requires its internal files
        '--collect-all=streamlit',
        '--collect-all=altair',
        '--collect-all=pandas',
        '--collect-all=polars',
        
        # Include our source code in the bundle
        '--add-data=app.py:.',
        '--add-data=src:src',
        
        # Hidden imports that PyInstaller might miss
        '--hidden-import=streamlit',
        '--hidden-import=src',
        '--hidden-import=pkg_resources.py2_warn',
        '--collect-all=jaraco',
        '--collect-all=pkg_resources',
        '--hidden-import=platformdirs',
        '--hidden-import=platformdirs',
        '--collect-all=platformdirs',
        '--collect-all=platformdirs',
        # MacOS specific sysconfig module often missed
        '--hidden-import=_sysconfigdata__darwin_darwin',
        # Fix lxml import error
        '--collect-all=lxml',
        # Fix rapidfuzz import error
        '--collect-all=rapidfuzz',
    ]
    
    print("🚀 Starting PyInstaller build...")
    PyInstaller.__main__.run(args)
    print("✅ Build complete!")
    
    # Post-build: Check if we need to copy META for testing
    dist_dir = Path("dist")
    meta_src = Path("META")
    
    print("\n📦 To distribute:")
    print("1. Locate the executable in 'dist/'")
    print("2. Zip it together with the 'META/' folder")
    print("\nNote: The user MUST have the 'META' folder in the same directory as the executable.")

if __name__ == "__main__":
    build()
