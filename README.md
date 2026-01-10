# Systematic Review Query Generator 🚀

**An advanced tool for converting natural language research questions into comprehensive, syntax-correct search queries for systematic reviews and meta-analyses.**

![Status](https://img.shields.io/badge/Status-Active-success)
![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-1.40+-red)

## 🌟 Features

- **Standardized PICO Extraction**: Uses LLMs (via NanoGPT) to intelligently break down research questions into **P**opulation, **I**ntervention, **C**omparison, and **O**utcome.
- **Sub-Concept Logic**: Goes beyond simple keywords by grouping synonyms into distinct sub-concepts (e.g., "Child" OR "Pediatric") and ANDing them with other concepts (e.g. "Migraine").
- **Deep Term Expansion**:
    - **MeSH Integration**: Automatically maps terms to Medical Subject Headings (MeSH 2026) including tree explosion.
    - **UMLS Synonyms**: Leverages the Unified Medical Language System to find synonyms from SNOMED-CT, RxNorm, and more.
- **Multi-Database Support**: Generates native syntax queries for:
    - PubMed
    - Embase
    - Cochrane Library
    - Web of Science
    - Scopus
    - Semantic Scholar (Relevance Search)
- **Interactive Review**: Full control to review, edit, and select which terms to include before generation.

## 🛠️ Installation

### Prerequisites
- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd search-query-tool
    ```

2.  **Install dependencies:**
    Using `uv` (faster, recommended):
    ```bash
    uv sync
    ```
    Or using standard pip:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Prepare Data Files (Critical Step):**
    The tool requires local copies of MeSH and UMLS databases. Create a `META/` directory in the project root and add:
    
    - **MeSH Data**: Download `desc2026.xml` (or latest) from [NLM MeSH Download](https://www.nlm.nih.gov/mesh/download/meshxml.html) and place it in `META/`.
    - **UMLS Data**: Download the full UMLS Metathesaurus (`MRCONSO.RRF`) from [UTS](https://uts.nlm.nih.gov/uts/) (requires license) and place it in `META/`.
    
    Structure should look like:
    ```
    search-query-tool/
    ├── app.py
    ├── META/
    │   ├── desc2026.xml       # Required for MeSH
    │   └── MRCONSO.RRF        # Required for UMLS
    └── ...
    ```

    *Note: The app will automatically convert `MRCONSO.RRF` to an optimized Parquet file on first run.*

4.  **API Key**:
    You need a **NanoGPT** API key for the LLM extraction features. You can enter this in the app UI or set it as an environment variable:
    ```bash
    export NANOGPT_API_KEY="your-key-here"
    ```

## 🚀 Usage

### 1. Start the App
```bash
./run.sh
# Or manually: streamlit run app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser.

### 2. The Workflow

**Step 1: Enter Research Question**
Type your question naturally. Example: *"Does propranolol reduce migraine frequency in children under 12?"*

**Step 2: Extract Concepts**
Click **Extract & Analyze**. The LLM will identify PICO categories and distinct sub-concepts.
*   *Correction*: If the LLM misses a nuance, you can manually edit terms.

**Step 3: Expand Terms**
Click **Expand with MeSH & UMLS**. The tool searches your local `META/` databases to find:
*   Official MeSH headings (e.g., mapping "heart attack" to "Myocardial Infarction").
*   Synonyms from UMLS (e.g., "MI", "Cardiovascular stroke").

**Step 4: Review & Refine**
Toggle specific MeSH terms or UMLS synonyms on/off. You have full granular control over the final query construction.

**Step 5: Generate Queries**
Click **Generate Final Queries** to produce syntax-specific strings for all selected databases. Copy them to your clipboard or download as a text file.

## 📦 Building Standalone App (One-Click Run)

You can package the app as a standalone executable (e.g., `.app` on Mac or `.exe` on Windows) for easy distribution.

### 1. Build
Run the build script:
```bash
uv run python build.py
```
This will create a `dist/` directory containing the executable.

### 2. Distribute
To share the app, you must zip **two items** together:
1.  The executable in `dist/` (e.g., `SearchTool` or `SearchTool.exe`)
2.  The `META/` folder (containing your database files)

> **Important**: The `META/` folder must remain typically in the same folder as the executable for the app to find the large database files.

> **OS Compatibility**: PyInstaller creates executables **only** for the OS it is run on. To give a Windows version to a colleague, you must run the build script on a Windows machine.

## 🧠 Search Logic Explained

The tool builds queries using a robust Boolean logic designed for high sensitivity:

1.  **Within a Sub-Concept (OR)**:
    All synonyms for a single idea are combined with OR.
    > `(Child OR "Pediatric patient" OR "Pediatrics"[MeSH])`

2.  **Between Sub-Concepts (AND)**:
    Different aspects of the same PICO category are combined with AND.
    > `(Child OR ...) AND (Migraine OR ...)`

3.  **Between Categories (AND)**:
    Population, Intervention, and Outcome blocks are combined with AND.
    > `(Population Block) AND (Intervention Block) AND (Outcome Block)`

## ⚙️ Configuration

Check the **Settings** sidebar for advanced controls:

| Setting | Description | Recommended |
|---------|-------------|-------------|
| **Include MeSH Preferred** | Uses standardized MeSH descriptors `[MeSH]` | ✅ Yes |
| **Include MeSH Entry Terms** | Adds MeSH "See Also" terms as free text | ✅ Yes (for sensitivity) |
| **Explode MeSH Tree** | Includes all child terms (e.g., "Heart Diseases" includes "Arrhythmias") | ⚠️ Use with caution |
| **Include UMLS Synonyms** | Adds synonyms from other vocabularies | ✅ Yes |
| **Min Fuzzy Score** | How strict the synonym matching should be (50-100) | 80-90 |
| **PubMed Proximity** | Uses `[tiab:~N]` to find words near each other | 2 |

## 📦 Project Structure

```
.
├── app.py                  # Main Streamlit application entry point
├── launcher.py             # Entry point for standalone executable
├── build.py                # PyInstaller build script
├── src/
│   ├── keyword_extractor.py # LLM interaction logic (NanoGPT)
│   ├── query_builder.py     # Syntax adapters for PubMed, Embase, etc.
│   ├── mesh_loader.py       # XML parser for MeSH descriptors
│   ├── umls_loader.py       # Polars-based loader for UMLS RRF files
│   └── models.py            # Pydantic data models
├── META/                   # Data directory (ignored by git)
│   ├── desc2026.xml        # MeSH XML (User provided)
│   └── MRCONSO.RRF         # UMLS Data (User provided)
├── run.sh                  # Helper script to launch app
└── restart.sh              # Helper script to kill & restart
```

## ⚠️ Troubleshooting

-   **"UMLS data not found"**: Ensure `MRCONSO.RRF` is exactly in the `META/` folder. The app creates `umls_filtered.parquet` automatically; if this fails, check your disk space and memory (UMLS is large).
-   **"MeSH XML not found"**: Ensure `desc2026.xml` is in `META/`.
-   **API Errors**: specific "NanoGPT" API keys are required. Check the "Settings" sidebar to validate your key.

## License

MIT License. Free to use for research and academic purposes.
