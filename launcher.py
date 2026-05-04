"""Portable launcher for Search Query Tool.

Binds Streamlit to 127.0.0.1 on an available port, opens the browser,
suppresses LAN/external URL display, and writes logs next to the executable.
"""

import sys
import os
import socket
import webbrowser
import time
import logging
import tempfile
import platform
from pathlib import Path
from streamlit.web import cli as st_cli


def resolve_path(path: str) -> str:
    """Resolve path to a bundled resource inside the PyInstaller archive."""
    if getattr(sys, '_MEIPASS', None):
        return os.path.join(sys._MEIPASS, path)
    return os.path.abspath(path)


def get_exe_dir() -> Path:
    """Return the directory containing the executable (or the project root in dev)."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def find_free_port(start: int = 8501, attempts: int = 50) -> int:
    """Find an available local TCP port starting at *start*."""
    for offset in range(attempts):
        port = start + offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"Could not find a free port in range {start}–{start + attempts - 1}")


def _candidate_log_dirs(exe_dir: Path) -> list[Path]:
    """Return a prioritised list of writable log directories to try."""
    candidates = [exe_dir / "logs"]

    system = platform.system()
    if system == "Windows":
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            candidates.append(Path(local_app) / "SearchQueryTool" / "logs")
    elif system == "Darwin":
        candidates.append(Path.home() / "Library" / "Logs" / "SearchQueryTool")

    candidates.append(Path(tempfile.gettempdir()) / "SearchQueryTool" / "logs")
    return candidates


def setup_logging(exe_dir: Path) -> logging.Logger:
    """Configure file logging, falling back gracefully if the exe directory is read-only.

    Try locations in order:
      1. <exe_dir>/logs/
      2. OS-specific user-writable directory
      3. System temp directory
      4. Console-only (if all file paths fail)
    """
    logger = logging.getLogger("launcher")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s")

    for log_dir in _candidate_log_dirs(exe_dir):
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "launcher.log"
            handler = logging.FileHandler(log_file, encoding="utf-8")
            handler.setFormatter(fmt)
            logger.addHandler(handler)
            logger.info("Log file: %s", log_file)
            return logger
        except OSError:
            continue

    # All file locations failed — fall back to console logging
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)
    logger.warning("Could not create log file; logging to console only.")
    return logger


if __name__ == "__main__":
    exe_dir = get_exe_dir()
    logger = setup_logging(exe_dir)

    # Set working directory to the executable location so that relative
    # paths (META/, logs/) resolve next to the app.
    os.chdir(exe_dir)
    logger.info("Working directory: %s", exe_dir)

    app_path = resolve_path("app.py")
    logger.info("App entry: %s", app_path)

    port = find_free_port()
    logger.info("Selected port: %d", port)

    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--global.developmentMode=false",
        f"--server.port={port}",
        "--server.address=127.0.0.1",
        # Suppress the "Network URL" / "External URL" display
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]

    url = f"http://127.0.0.1:{port}"
    logger.info("Opening browser at %s", url)

    # Open the browser after a short delay so Streamlit has time to start
    import threading

    def _open_browser():
        time.sleep(2)
        webbrowser.open(url)

    threading.Thread(target=_open_browser, daemon=True).start()

    try:
        sys.exit(st_cli.main())
    except SystemExit as exc:
        code = exc.code if exc.code is not None else 0
        if code != 0:
            logger.error("Streamlit exited with code %s", code)
            sys.exit(code)
        # Normal shutdown (code 0 or None) — exit cleanly
    except Exception:
        logger.exception("Streamlit crashed")
        raise
