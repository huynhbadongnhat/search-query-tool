"""Assemble the portable distribution from PyInstaller output.

This script does NOT run PyInstaller.  It expects the onedir output at
``dist/SearchQueryTool/`` (produced by ``SearchTool.spec``) and assembles a
clean, distributable folder at ``portable_dist/SearchQueryTool/``.

Usage (from project root, after running PyInstaller):
    uv run python build.py
"""

import shutil
import platform
from pathlib import Path


def assemble():
    """Copy PyInstaller output and add portable-distribution extras."""

    dist_dir = Path("dist") / "SearchQueryTool"
    portable_dist = Path("portable_dist") / "SearchQueryTool"

    if not dist_dir.exists():
        print(
            f"Expected PyInstaller output not found at {dist_dir}.\n"
            "   Run PyInstaller first:\n"
            "     uv run pyinstaller SearchTool.spec --noconfirm --clean\n"
        )
        raise SystemExit(1)

    # Clean previous portable_dist
    if portable_dist.exists():
        shutil.rmtree(portable_dist)

    # Copy the entire onedir output
    shutil.copytree(dist_dir, portable_dist)

    # Add META/ placeholder with README
    meta_dir = portable_dist / "META"
    meta_dir.mkdir(exist_ok=True)
    (meta_dir / "README_META.txt").write_text(
        "Optional local UMLS / MeSH data files.\n\n"
        "Place the following files here for offline term expansion:\n"
        "  - desc2026.xml     (MeSH Descriptors XML)\n"
        "  - MRCONSO.RRF      (UMLS Metathesaurus, will be preprocessed on first run)\n"
        "  - umls_filtered.parquet  (preprocessed UMLS subset)\n\n"
        "These files are NOT required when using the UMLS API mode (default).\n",
        encoding="utf-8",
    )

    # Add .env.example
    (portable_dist / ".env.example").write_text(
        "# Optional: set API keys as environment variables\n"
        "# NANOGPT_API_KEY=your_nanogpt_key_here\n"
        "# UMLS_API_KEY=your_umls_key_here\n",
        encoding="utf-8",
    )

    # Add empty logs/ dir
    (portable_dist / "logs").mkdir(exist_ok=True)

    # Platform-specific README
    if platform.system() == "Windows":
        readme = portable_dist / "README_RUN_WINDOWS.txt"
        readme.write_text(
            "Search Query Tool - Windows\n"
            "===========================\n\n"
            "1. Double-click SearchQueryTool.exe\n"
            "2. A browser tab will open at http://127.0.0.1:8501 (or next free port)\n"
            "3. Enter your API keys in the sidebar\n\n"
            "Optional: place UMLS/MeSH files in the META/ folder for offline mode.\n",
            encoding="utf-8",
        )
    else:
        readme = portable_dist / "README_RUN_MACOS.txt"
        readme.write_text(
            "Search Query Tool - macOS\n"
            "========================\n\n"
            "1. Open Terminal and cd to this folder\n"
            "2. Run: ./SearchQueryTool\n"
            "3. A browser tab will open at http://127.0.0.1:8501 (or next free port)\n"
            "4. Enter your API keys in the sidebar\n\n"
            "Optional: place UMLS/MeSH files in the META/ folder for offline mode.\n\n"
            "If macOS blocks the app, go to System Settings > Privacy & Security > Allow.\n",
            encoding="utf-8",
        )

    print(f"\nPortable distribution assembled at: {portable_dist.resolve()}")
    print("   Contents:")
    for p in sorted(portable_dist.rglob("*")):
        if p.is_file():
            rel = p.relative_to(portable_dist)
            # Only show top-level and META/ files, skip _internal/ bulk
            parts = rel.parts
            if len(parts) <= 2 or parts[0] == "META":
                print(f"     {rel}")
    print(f"\n   To distribute, zip the '{portable_dist.name}/' folder.")


if __name__ == "__main__":
    assemble()
