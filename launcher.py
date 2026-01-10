import sys
import os
from streamlit.web import cli as st_cli

def resolve_path(path):
    """
    Resolve path to resource, handling both dev environment and PyInstaller bundle.
    """
    if getattr(sys, '_MEIPASS', None):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        return os.path.join(sys._MEIPASS, path)
    return os.path.abspath(path)

if __name__ == "__main__":
    # When running as an executable, we need to tell Streamlit 
    # where the app.py file is located within the bundle
    app_path = resolve_path("app.py")
    
    # We also need to ensure the working directory is set to where the executable is
    # so that relative paths to external data (META/) work correctly.
    if getattr(sys, 'frozen', False):
        # If frozen, the executable is at sys.executable
        # On Mac .app bundles, this might be inside Contents/MacOS
        # We want the directory containing the app bundle or executable
        exe_dir = os.path.dirname(sys.executable)
        os.chdir(exe_dir)
    
    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--global.developmentMode=false",
    ]
    
    sys.exit(st_cli.main())
