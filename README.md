# Systematic Review Query Generator

**An advanced tool for converting natural language research questions into comprehensive, syntax-correct search queries for systematic reviews and meta-analyses.**

![Status](https://img.shields.io/badge/Status-Active-success)
![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-1.40+-red)

## Features

- **Standardized PICO Extraction**: Uses LLMs (via NanoGPT) to intelligently break down research questions into **P**opulation, **I**ntervention, **C**omparison, and **O**utcome.
- **Smart Semantic Decomposition**:
    - **Core vs. Modifier**: Automatically separates core concepts (e.g., "Steroids") from modifiers (e.g., "Intravenous") to prevent search bias.
    - **Route Handling**: Intelligent backoff logic strips pharmaceutical routes to ensure drug concepts are found even when phrased specifically (e.g., "Oral Antibiotics" → Finds "Antibiotics").
- **Deep Term Expansion**:
    - **MeSH Integration**: Automatically maps terms to Medical Subject Headings (MeSH 2026) including tree explosion.
    - **UMLS API Integration**: Leverages the UMLS API to find authoritative synonyms, filtering out non-English terms and irrelevant clinical formulations.
- **Multi-Database Support**: Generates native syntax queries for:
    - PubMed (supports proximity `[Title/Abstract:~N]`)
    - Embase
    - Cochrane Library
    - Web of Science
    - Scopus
    - Semantic Scholar (Relevance Search)
- **Interactive Review**: Full control to review, edit, and select which terms to include before generation.

## Installation

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
    The tool requires local copies of MeSH and optionally UMLS databases. Create a `META/` directory in the project root and add:
    
    - **MeSH Data**: Download `desc2026.xml` (or latest) from [NLM MeSH Download](https://www.nlm.nih.gov/mesh/download/meshxml.html) and place it in `META/`.
    - **UMLS Data**: Download the full UMLS Metathesaurus (`MRCONSO.RRF`) from [UTS](https://uts.nlm.nih.gov/uts/) (requires license) and place it in `META/`.
    
    Structure should look like:
    ```
    search-query-tool/
    ├── app.py
    ├── META/
    │   ├── desc2026.xml       # Required for MeSH
    │   └── MRCONSO.RRF        # Required for local fallback
    └── ...
    ```

    *Note: The app will automatically convert `MRCONSO.RRF` to an optimized Parquet file on first run.*

4.  **API Keys**:
    - **NanoGPT API Key**: Required for LLM extraction.
    - **UMLS API Key**: Required for "Smart Search" expansion. Get yours from [UTS Profile](https://uts.nlm.nih.gov/uts/profile).
    
    You can enter these in the app UI (they will be saved securely) or set as environment variables:
    ```bash
    export NANOGPT_API_KEY="your-llm-key"
    export UMLS_API_KEY="your-umls-key"
    ```

## Usage

### 1. Start the App
```bash
./run.sh
# Or manually: streamlit run app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser.

### 2. The Workflow

**Step 1: Enter Research Question**
Type your question naturally. Example: *"Does intravenous propranolol reduce migraine frequency in children under 12?"*

**Step 2: Extract Concepts**
Click **Extract & Analyze**. The LLM will identify PICO categories and distinct sub-concepts.
*   *Smart Logic*: It separates "intravenous" as a modifier, keeping "propranolol" as the core concept for better expansion.

**Step 3: Expand Terms**
Click **Expand with MeSH & UMLS**. The tool searches:
*   **MeSH**: Local lookup for official headings.
*   **UMLS API**: Live lookup for synonyms, filtering out noise words and non-English terms.

**Step 4: Review & Refine**
Toggle specific MeSH terms or UMLS synonyms on/off. You can also add your own custom synonyms.

**Step 5: Generate Queries**
Click **Generate Final Queries** to produce syntax-specific strings for all selected databases. Copy them to your clipboard.

## Building Standalone App (One-Click Run)

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

## Search Logic Explained

The tool builds queries using a robust Boolean logic designed for high sensitivity:

1.  **Semantic Decomposition**:
    Core Concept and Modifiers are handled distinctly:
    > `((Core Concept OR Expansions...) AND Modifier)`
    *Example*: "Intravenous Steroids" becomes `(("Steroids"[MeSH] OR "Corticosteroids"...) AND "intravenous"[Title/Abstract])`

2.  **Within a Sub-Concept (OR)**:
    All synonyms for a single idea are combined with OR.

3.  **Between Sub-Concepts (AND)**:
    Different aspects of the same PICO category are combined with AND.

4.  **Between Categories (AND)**:
    Population, Intervention, and Outcome blocks are combined with AND.

## Configuration

Check the **Settings** sidebar for advanced controls:

| Setting | Description | Recommended |
|---------|-------------|-------------|
| **Include MeSH Preferred** | Uses standardized MeSH descriptors `[MeSH]` | ✅ Yes |
| **Include MeSH Entry Terms** | Adds MeSH "See Also" terms as free text | ✅ Yes (for sensitivity) |
| **Explode MeSH Tree** | Includes all child terms (e.g., "Heart Diseases" includes "Arrhythmias") | ⚠️ Use with caution |
| **Include UMLS Synonyms** | Adds synonyms from other vocabularies via API | ✅ Yes |
| **Min Fuzzy Score** | How strict the synonym matching should be (50-100) | 80-90 |
| **PubMed Proximity** | Uses `[Title/Abstract:~N]` to find words near each other | 2 |

## Troubleshooting

-   **"UMLS data not found"**: Ensure `MRCONSO.RRF` is exactly in the `META/` folder if using local fallback.
-   **"MeSH XML not found"**: Ensure `desc2026.xml` is in `META/`.
-   **API Errors**:
    -   **400/401**: Check your `UMLS_API_KEY`. It must be a valid API key from UTS, not your password.
    -   **Validation Error**: Check your `NANOGPT_API_KEY`.

## License

MIT License. Free to use for research and academic purposes.
