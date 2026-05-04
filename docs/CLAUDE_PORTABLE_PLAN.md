# Claude Execution Plan: Portable USB Builds

## Goal

Create portable, self-contained builds of the Search Query Tool that can run from a USB drive on Windows and macOS machines that have only internet access and a browser. The app must not be hosted remotely.

## Key Constraints

- A single executable cannot reliably support both Windows and macOS. Build separate distributions per OS.
- macOS may need separate Apple Silicon and Intel builds, or a documented universal-build process.
- UMLS MRCONSO redistribution can be license-sensitive and very large. Default portable mode should use UMLS API, with local `META/` files as optional user-supplied data.
- The local app must bind only to `127.0.0.1`; do not expose the Streamlit server to the LAN or internet.
- Do not save API keys to the USB by default. Session-only key entry should be the default secure behavior.

## Recommended Architecture

Package the app as OS-specific local desktop launchers:

- `SearchQueryTool-Windows-x64/`
  - `SearchQueryTool.exe`
  - `_internal/` dependencies if using PyInstaller onedir
  - optional `META/`
  - `README_RUN_WINDOWS.txt`
- `SearchQueryTool-macOS-arm64/`
  - `SearchQueryTool.app` or executable folder
  - optional `META/`
  - `README_RUN_MACOS.txt`
- `SearchQueryTool-macOS-x64/`
  - same structure for Intel Macs if needed

Use PyInstaller `onedir` first, not `onefile`. `onedir` is larger but usually more reliable for Streamlit, avoids repeated extraction delays, and is less likely to trigger antivirus false positives.

## Implementation Tasks

1. **Harden the launcher**
   - Update `launcher.py` to bind Streamlit to `127.0.0.1`.
   - Pick an available local port, starting at `8501`, falling back to the next free port.
   - Open the browser to `http://127.0.0.1:<port>`.
   - Suppress LAN/external URL display.
   - Write logs next to the executable under `logs/`.

2. **Make runtime paths portable**
   - Resolve app resources from PyInstaller `_MEIPASS`.
   - Resolve user-supplied data from the executable directory first: `./META/desc2026.xml`, `./META/MRCONSO.RRF`, `./META/umls_filtered.parquet`.
   - Avoid writing generated cache files outside the app folder unless the user explicitly chooses that.

3. **Secure API-key handling**
   - Default to session-only API key entry.
   - Add a setting: `Remember keys on this computer`.
   - If persistent storage is needed, prefer OS keychain via Python `keyring`; do not silently save plaintext keys to USB.
   - Keep environment variables and Streamlit secrets supported for advanced users.

4. **Default portable mode to API expansion**
   - On first run, default `Term Expansion Source` to `UMLS API`.
   - Show local file mode only as optional advanced/offline mode.
   - If local mode is selected and `META/` is missing, show a precise missing-file message.

5. **Update build configuration**
   - Replace `--onefile` with `--onedir` for the primary portable build.
   - Remove duplicated `platformdirs` collect options in `build.py` and `SearchTool.spec`.
   - Add OS-specific build scripts:
     - `scripts/build_windows.ps1`
     - `scripts/build_macos.sh`
   - Add `--name=SearchQueryTool`.
   - Include `app.py`, `src/`, and any Streamlit static assets needed by PyInstaller.

6. **Create release folders**
   - After PyInstaller, assemble a clean `portable_dist/` folder.
   - Include the executable folder, README, sample `.env.example`, and an empty `META/README_META.txt`.
   - Zip each OS build separately.

7. **Smoke-test on clean machines**
   - Windows 10/11 VM with no Python installed.
   - macOS Apple Silicon with no Python installed.
   - macOS Intel if supporting Intel users.
   - Confirm:
     - app starts from USB path with spaces
     - browser opens to localhost
     - no server is exposed on LAN
     - API key can be entered without saving
     - UMLS API mode works
     - local `META/` mode works when data files are supplied

## Verification Commands

Run before packaging:

```powershell
uv run python -m compileall app.py src tests
uv run python -m unittest discover -s tests
uv run streamlit run app.py
```

Windows build:

```powershell
uv sync --group dev
uv run pyinstaller SearchTool.spec --noconfirm --clean
```

macOS build:

```bash
uv sync --group dev
uv run pyinstaller SearchTool.spec --noconfirm --clean
```

## Acceptance Criteria

- A non-technical user can copy one OS-specific folder to a USB drive and run the app without installing Python.
- The app opens in the default browser on `127.0.0.1`.
- No external hosting, tunnel, LAN binding, or cloud deployment is used.
- API keys are not persisted unless the user explicitly opts in.
- Local licensed data is optional and not bundled by default.
