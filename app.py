"""MeSH Search Query Tool - Streamlit Application."""

import streamlit as st
import requests
import os
from datetime import datetime
from pathlib import Path
from src.models import (
    Database, DataSource, SearchSettings, SubConcept, ExtractedPICO, MeSHDescriptor
)
from src.mesh_loader import MeSHLoader
from src.umls_loader import UMLSLoader
from src.keyword_extractor import KeywordExtractor
from src.query_builder import QueryBuilder
from src.api_clients import UMLSClient, RateLimiter
from src.term_utils import dedupe_terms, split_comma_terms, normalize_term

# Available NanoGPT models - fallback list if API fetch fails
DEFAULT_NANOGPT_MODELS = [
    "Qwen/Qwen3-VL-235B-A22B-Instruct",
    "deepseek/deepseek-r1",
    "deepseek/deepseek-chat",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "anthropic/claude-sonnet-4",
    "google/gemini-2.0-flash",
]

@st.cache_data(ttl=3600)
def fetch_nanogpt_models(api_key: str) -> list[str]:
    """Fetch available models from NanoGPT subscription API."""
    if not api_key:
        return DEFAULT_NANOGPT_MODELS
    
    try:
        response = requests.get(
            "https://nano-gpt.com/api/subscription/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                models = []
                for item in data:
                    if isinstance(item, str):
                        models.append(item)
                    elif isinstance(item, dict):
                        model_id = item.get("id") or item.get("name") or item.get("model")
                        if model_id:
                            models.append(model_id)
                return models if models else DEFAULT_NANOGPT_MODELS
            elif isinstance(data, dict):
                models = data.get("models") or data.get("data") or []
                if isinstance(models, list):
                    result = []
                    for item in models:
                        if isinstance(item, str):
                            result.append(item)
                        elif isinstance(item, dict):
                            model_id = item.get("id") or item.get("name") or item.get("model")
                            if model_id:
                                result.append(model_id)
                    return result if result else DEFAULT_NANOGPT_MODELS
        return DEFAULT_NANOGPT_MODELS
    except Exception:
        return DEFAULT_NANOGPT_MODELS


# =============================================================================
# Configuration
# =============================================================================

st.set_page_config(
    page_title="MeSH Search Query Tool",
    page_icon=None,
    layout="wide"
)

# Constants
MESH_XML_PATH = Path("META/desc2026.xml")
UMLS_RRF_PATH = Path("META/MRCONSO.RRF")
UMLS_PARQUET_PATH = Path("META/umls_filtered.parquet")

# API Key storage - stored in user's home directory for security
CONFIG_DIR = Path.home() / ".mesh_query_tool"
API_KEY_FILE = CONFIG_DIR / "api_key.txt"
UMLS_API_KEY_FILE = CONFIG_DIR / "umls_api_key.txt"

# =============================================================================
# API Key Management
# =============================================================================

def load_saved_api_key() -> str:
    """Load API key from secure local storage."""
    try:
        if API_KEY_FILE.exists():
            return API_KEY_FILE.read_text().strip()
    except Exception:
        pass
    return ""

def save_api_key(api_key: str) -> bool:
    """Save API key to secure local storage."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        API_KEY_FILE.write_text(api_key)
        # Set file permissions to owner-only (Unix)
        try:
            API_KEY_FILE.chmod(0o600)
        except Exception:
            pass  # Windows doesn't support Unix permissions
        return True
    except Exception:
        return False

def clear_saved_api_key() -> bool:
    """Remove saved API key."""
    try:
        if API_KEY_FILE.exists():
            API_KEY_FILE.unlink()
        return True
    except Exception:
        return False


def get_secret_value(name: str) -> str:
    """Read a Streamlit secret without requiring secrets.toml to exist."""
    try:
        value = st.secrets.get(name)
    except Exception:
        return ""
    return str(value).strip() if value else ""


def get_api_key() -> str:
    """Get API key from various sources (priority order)."""
    # 1. Session state (current session override)
    if st.session_state.get("api_key"):
        return st.session_state["api_key"]
    # 2. Streamlit secrets (for deployment)
    secret_key = get_secret_value("NANOGPT_API_KEY")
    if secret_key:
        return secret_key
    # 3. Environment variable
    if os.environ.get("NANOGPT_API_KEY"):
        return os.environ["NANOGPT_API_KEY"]
    # 4. Saved local config
    return load_saved_api_key()

# --- UMLS API Key Management ---

def load_saved_umls_api_key() -> str:
    """Load UMLS API key from secure local storage."""
    try:
        if UMLS_API_KEY_FILE.exists():
            return UMLS_API_KEY_FILE.read_text().strip()
    except Exception:
        pass
    return ""

def save_umls_api_key(api_key: str) -> bool:
    """Save UMLS API key to secure local storage."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        UMLS_API_KEY_FILE.write_text(api_key)
        try:
            UMLS_API_KEY_FILE.chmod(0o600)
        except Exception:
            pass
        return True
    except Exception:
        return False

def clear_saved_umls_api_key() -> bool:
    """Remove saved UMLS API key."""
    try:
        if UMLS_API_KEY_FILE.exists():
            UMLS_API_KEY_FILE.unlink()
        return True
    except Exception:
        return False

def get_umls_api_key() -> str:
    """Get UMLS API key from various sources."""
    if st.session_state.get("umls_api_key"):
        return st.session_state["umls_api_key"]
    secret_key = get_secret_value("UMLS_API_KEY")
    if secret_key:
        return secret_key
    if os.environ.get("UMLS_API_KEY"):
        return os.environ["UMLS_API_KEY"]
    return load_saved_umls_api_key()

# =============================================================================
# Helper Functions
# =============================================================================

def get_mesh_loader():
    """Get or create MeSH loader."""
    if "mesh_loader" not in st.session_state:
        loader = MeSHLoader(MESH_XML_PATH)
        loader.load()
        st.session_state["mesh_loader"] = loader
    return st.session_state["mesh_loader"]

def get_umls_loader():
    """Get or create UMLS loader."""
    if "umls_loader" not in st.session_state:
        if not UMLS_PARQUET_PATH.exists():
            if UMLS_RRF_PATH.exists():
                with st.spinner("Preprocessing UMLS data (one-time setup)..."):
                    temp_loader = UMLSLoader(rrf_path=UMLS_RRF_PATH)
                    temp_loader.preprocess_rrf_to_parquet(UMLS_PARQUET_PATH)
            else:
                st.error(f"UMLS data not found at {UMLS_RRF_PATH}")
                return None
        
        loader = UMLSLoader(parquet_path=UMLS_PARQUET_PATH)
        st.session_state["umls_loader"] = loader
    return st.session_state["umls_loader"]

def get_keyword_extractor():
    """Get keyword extractor with current model settings."""
    api_key = get_api_key()
    model = st.session_state.get("selected_model", DEFAULT_NANOGPT_MODELS[0])
    return KeywordExtractor(api_key=api_key, model=model)

def get_search_settings() -> SearchSettings:
    """Build SearchSettings from session state."""
    return SearchSettings(
        include_mesh_preferred=st.session_state.get("include_mesh_preferred", True),
        include_mesh_entry_terms=st.session_state.get("include_mesh_entry_terms", True),
        explode_mesh_tree=st.session_state.get("explode_mesh_tree", False),
        include_umls_synonyms=st.session_state.get("include_umls_synonyms", True),
        min_fuzzy_score=st.session_state.get("min_fuzzy_score", 90),
        include_title_abstract=st.session_state.get("include_title_abstract", True),
        proximity_distance=st.session_state.get("proximity_distance", 2)
    )

def test_nanogpt_connection(api_key: str) -> tuple[bool, str]:
    """Test connection to NanoGPT API."""
    if not api_key:
        return False, "No API key provided"
    try:
        response = requests.get(
            "https://nano-gpt.com/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5
        )
        if response.status_code == 200:
            return True, "Connected successfully"
        else:
            return False, f"Error: {response.status_code}"
    except requests.exceptions.Timeout:
        return False, "Connection timeout"
    except Exception as e:
        return False, f"Error: {str(e)}"

# =============================================================================
# Sidebar
# =============================================================================

with st.sidebar:
    st.title("Settings")
    
    # ==========================================================================
    # 1. UMLS Data Management (Local Files)
    # ==========================================================================
    st.subheader("Data Management")
    
    if UMLS_PARQUET_PATH.exists():
        st.success("UMLS data ready (Parquet)")
    else:
        if UMLS_RRF_PATH.exists():
            st.warning("UMLS RRF found but not preprocessed")
            if st.button("Preprocess UMLS to Parquet", use_container_width=True):
                with st.spinner("Preprocessing UMLS data (this may take a few minutes)..."):
                    temp_loader = UMLSLoader(rrf_path=UMLS_RRF_PATH)
                    temp_loader.preprocess_rrf_to_parquet(UMLS_PARQUET_PATH)
                st.success("UMLS preprocessing complete!")
                st.rerun()
        else:
            st.info(f"UMLS data not found at {UMLS_RRF_PATH}")
    
    # Restart & Clear Cache
    if st.button("Clear Cache & Restart", use_container_width=True, type="secondary"):
        st.cache_data.clear()
        st.cache_resource.clear()
        # Clear session state except API keys
        keys_to_keep = {"api_key", "umls_api_key"}
        for key in list(st.session_state.keys()):
            if key not in keys_to_keep:
                del st.session_state[key]
        st.success("Cache cleared!")
        st.rerun()
    
    st.divider()
    
    # ==========================================================================
    # 2. Target Databases
    # ==========================================================================
    st.subheader("Target Databases")
    
    db_pubmed = st.checkbox("PubMed", value=True)
    db_embase = st.checkbox("Embase", value=True)
    db_cochrane = st.checkbox("Cochrane", value=True)
    db_wos = st.checkbox("Web of Science", value=True)
    db_scopus = st.checkbox("Scopus", value=True)
    db_sem_scholar = st.checkbox("Semantic Scholar", value=True, help="Uses relevance search with concept keywords only")
    
    selected_dbs = []
    if db_pubmed: selected_dbs.append(Database.PUBMED)
    if db_embase: selected_dbs.append(Database.EMBASE)
    if db_cochrane: selected_dbs.append(Database.COCHRANE)
    if db_wos: selected_dbs.append(Database.WEB_OF_SCIENCE)
    if db_scopus: selected_dbs.append(Database.SCOPUS)
    if db_sem_scholar: selected_dbs.append(Database.SEMANTIC_SCHOLAR)
    
    st.divider()
    
    # ==========================================================================
    # 3. Search Settings
    # ==========================================================================
    st.subheader("Search Settings")
    
    # Presets
    preset = st.selectbox(
        "Quick Preset",
        options=["Custom", "High Sensitivity", "Balanced", "High Precision"],
        index=1,
        help="Choose a preset or customize settings below"
    )
    
    if preset == "High Sensitivity":
        default_mesh_pref, default_mesh_entry = True, True
        default_explode, default_umls = True, True
        default_fuzzy = 70
    elif preset == "High Precision":
        default_mesh_pref, default_mesh_entry = True, False
        default_explode, default_umls = False, False
        default_fuzzy = 90
    else:  # Balanced or Custom
        default_mesh_pref, default_mesh_entry = True, True
        default_explode, default_umls = False, True
        default_fuzzy = 80
    
    # Show options in an expander for cleaner UI
    with st.expander("Advanced Options", expanded=(preset == "Custom")):
        st.markdown("**MeSH Settings**")
        
        include_mesh_preferred = st.checkbox(
            "Include MeSH Preferred Terms",
            value=default_mesh_pref,
            help="Adds official MeSH headings (e.g., 'Ascorbic Acid' for Vitamin C). "
                 "Always recommended - these are standardized medical terms."
        )
        st.session_state["include_mesh_preferred"] = include_mesh_preferred
        
        include_mesh_entry_terms = st.checkbox(
            "Include MeSH Entry Terms (Synonyms)",
            value=default_mesh_entry,
            help="Adds synonyms from MeSH (e.g., 'Vitamin C', 'L-Ascorbic Acid'). "
                 "Enable for comprehensive searches."
        )
        st.session_state["include_mesh_entry_terms"] = include_mesh_entry_terms
        
        explode_mesh_tree = st.checkbox(
            "Explode MeSH Tree (Include Children)",
            value=default_explode,
            help="Includes all narrower/child terms in the MeSH hierarchy. "
                 "E.g., 'Heart Diseases' exploded includes 'Myocardial Infarction', etc."
        )
        st.session_state["explode_mesh_tree"] = explode_mesh_tree
        
        st.markdown("**UMLS Settings**")
        
        include_umls_synonyms = st.checkbox(
            "Include UMLS Synonyms",
            value=default_umls,
            help="Adds synonyms from UMLS (SNOMED-CT, RxNorm, etc.) for comprehensive coverage."
        )
        st.session_state["include_umls_synonyms"] = include_umls_synonyms
        
        st.markdown("**Match Quality**")
        
        min_fuzzy_score = st.slider(
            "Minimum Match Score",
            min_value=50,
            max_value=100,
            value=default_fuzzy,
            step=5,
            help="Higher = stricter matching, fewer results. Lower = looser matching, more results."
        )
        st.session_state["min_fuzzy_score"] = min_fuzzy_score
        
        st.markdown("**PubMed Proximity Search**")
        
        proximity_distance = st.slider(
            "Word Distance (PubMed only)",
            min_value=0,
            max_value=5,
            value=2,
            step=1,
            help="For multi-word phrases, allows words to appear with N words between them. 0 = disabled."
        )
        st.session_state["proximity_distance"] = proximity_distance
        
        st.markdown("**Text Search**")
        
        include_title_abstract = st.checkbox(
            "Search Title & Abstract",
            value=True,
            help="Searches in title and abstract fields. Standard practice for most searches."
        )
        st.session_state["include_title_abstract"] = include_title_abstract
    
    st.divider()
    
    # ==========================================================================
    # 4. API Settings (NanoGPT + Data Source + UMLS API)
    # ==========================================================================
    st.subheader("API Configuration")
    
    # --- NanoGPT API Key ---
    st.markdown("**NanoGPT API**")
    
    # Get current key from various sources
    current_key = get_api_key()
    saved_key_exists = API_KEY_FILE.exists()
    
    # Show source indicator
    if get_secret_value("NANOGPT_API_KEY"):
        st.caption("Using key from secrets.toml")
    elif os.environ.get("NANOGPT_API_KEY"):
        st.caption("Using key from environment variable")
    elif saved_key_exists:
        st.caption("Using saved key from local config")
    st.caption("Saved keys are written to a local plaintext file. Prefer environment variables or Streamlit secrets on shared machines.")
    
    # API key input
    api_key_input = st.text_input(
        "NanoGPT API Key", 
        type="password",
        value=current_key,
        help="Enter your NanoGPT API key. Keys can be saved locally for convenience.",
        placeholder="Enter API key..."
    )
    
    # Update session state if changed
    if api_key_input:
        st.session_state["api_key"] = api_key_input
    
    # Save/Clear/Test buttons
    col_save, col_clear = st.columns(2)
    with col_save:
        if st.button("Save Key", use_container_width=True, disabled=not api_key_input):
            if save_api_key(api_key_input):
                st.success("Saved!")
            else:
                st.error("Failed to save")
    
    with col_clear:
        if st.button("Clear", use_container_width=True, disabled=not saved_key_exists):
            if clear_saved_api_key():
                st.session_state["api_key"] = ""
                st.success("Cleared!")
                st.rerun()
    
    # Connection test button
    if st.button("Test Connection", use_container_width=True):
        with st.spinner("Testing..."):
            success, message = test_nanogpt_connection(api_key_input)
            if success:
                st.success(message)
            else:
                st.error(message)
    
    # --- LLM Settings ---
    st.markdown("**LLM Settings**")
    
    available_models = fetch_nanogpt_models(api_key_input)
    
    # Find default model in list, or use index 0
    default_model = "Qwen/Qwen3-VL-235B-A22B-Instruct"
    try:
        default_index = available_models.index(default_model)
    except ValueError:
        default_index = 0  # Fallback to first if preferred not found
    
    col_model, col_refresh = st.columns([4, 1])
    with col_model:
        selected_model = st.selectbox(
            "Model",
            options=available_models,
            index=default_index,
            help=f"Select the LLM model for keyword extraction ({len(available_models)} available)"
        )
        st.session_state["selected_model"] = selected_model
    
    with col_refresh:
        if st.button("Refresh", help="Refresh models list", key="refresh_models"):
            fetch_nanogpt_models.clear()
            st.rerun()
    
    # Temperature and Top-p sliders
    col_temp, col_topp = st.columns(2)
    with col_temp:
        temperature = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=1.0,
            value=0.1,
            step=0.05,
            help="Lower = more deterministic"
        )
        st.session_state["temperature"] = temperature
    
    with col_topp:
        top_p = st.slider(
            "Top-p",
            min_value=0.0,
            max_value=1.0,
            value=0.3,
            step=0.05,
            help="Lower = more focused"
        )
        st.session_state["top_p"] = top_p
    
    # --- Data Source Selection ---
    st.markdown("**Data Source**")
    
    data_source = st.radio(
        "Term Expansion Source",
        options=["Local Files", "UMLS API"],
        index=0,
        help="Local: Uses META/ folder (MeSH XML + UMLS Parquet). "
             "API: Uses UMLS REST API (requires API key, no local files needed)"
    )
    st.session_state["data_source"] = DataSource.LOCAL if data_source == "Local Files" else DataSource.API
    
    # UMLS API Key (only shown when API mode selected)
    if st.session_state["data_source"] == DataSource.API:
        st.markdown("**UMLS API Key**")
        
        # Load saved UMLS key
        current_umls_key = get_umls_api_key()
        saved_umls_key_exists = UMLS_API_KEY_FILE.exists()
        st.caption("Saved UMLS keys are written to a local plaintext file. Prefer environment variables or Streamlit secrets on shared machines.")
        
        umls_api_key = st.text_input(
            "UMLS API Key",
            type="password",
            value=current_umls_key,
            help="Get your key from UTS (https://uts.nlm.nih.gov/uts/)",
            placeholder="Enter UMLS API key..."
        )
        
        if umls_api_key:
            st.session_state["umls_api_key"] = umls_api_key
        
        # Save / Clear buttons
        col_save, col_clear = st.columns(2)
        with col_save:
            if st.button("Save UMLS Key", use_container_width=True, disabled=not umls_api_key):
                if save_umls_api_key(umls_api_key):
                    st.success("UMLS key saved!")
                else:
                    st.error("Failed to save key")
        with col_clear:
            if st.button("Clear UMLS Key", use_container_width=True, disabled=not saved_umls_key_exists):
                if clear_saved_umls_api_key():
                    st.session_state["umls_api_key"] = ""
                    st.info("Key cleared")
                    st.rerun()
        
        if not umls_api_key:
            st.warning("UMLS API key required for API mode")

# =============================================================================
# Main Content
# =============================================================================

st.title("Systematic Review Query Generator")
st.markdown("""
Convert natural language research questions into comprehensive search queries 
for multiple literature databases. **Now with sub-concept grouping for accurate AND/OR logic!**
""")

# =============================================================================
# Helper Callbacks
# =============================================================================

def clear_prefixed_state(prefixes: tuple[str, ...]) -> None:
    """Remove dynamic widget state created from variable PICO structures."""
    for key in list(st.session_state.keys()):
        if key.startswith(prefixes):
            del st.session_state[key]


def clear_all_callback():
    """Callback to clear all state."""
    keys_to_clear = [
        "extracted_pico", "expanded_pico", "queries", "expansion_done",
        "api_search_done", "api_search_pico", "cui_candidates", "mesh_backbone_terms",
        "query_audit_rows", "query_question", "original_question",
        "llm_raw_response", "llm_error", "llm_used_fallback"
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]
    clear_prefixed_state((
        "name_", "core_", "modifier_", "direction_", "terms_",
        "use_mesh_", "umls_sel_", "manual_terms_", "cui_select_", "show_all_",
    ))
    st.session_state["clear_counter"] = st.session_state.get("clear_counter", 0) + 1


CATEGORY_KEYS = ["population", "intervention", "comparison", "outcome", "other"]


def clear_downstream_state() -> None:
    """Clear outputs that are invalidated by concept edits or a new extraction."""
    for key in [
        "expanded_pico", "queries", "expansion_done", "api_search_done",
        "cui_candidates", "api_search_pico", "mesh_backbone_terms", "query_audit_rows",
    ]:
        st.session_state.pop(key, None)


def add_subconcept(cat_key: str) -> None:
    pico = st.session_state["extracted_pico"]
    getattr(pico, cat_key).append(
        SubConcept(
            name="manual",
            core_concept="",
            original_term="",
            expanded_terms=[],
            explanation="Added during manual audit.",
        )
    )
    clear_prefixed_state(("name_", "core_", "modifier_", "direction_", "terms_"))
    clear_downstream_state()


def remove_subconcept(cat_key: str, idx: int) -> None:
    pico = st.session_state["extracted_pico"]
    sub_concepts = getattr(pico, cat_key)
    if 0 <= idx < len(sub_concepts):
        del sub_concepts[idx]
        clear_prefixed_state(("name_", "core_", "modifier_", "direction_", "terms_"))
        clear_downstream_state()


def sync_subconcept_from_inputs(sc: SubConcept, cat_key: str, idx: int) -> None:
    """Write audited Streamlit inputs back to the PICO model."""
    core = normalize_term(st.session_state.get(f"core_{cat_key}_{idx}", sc.core_concept))
    sc.name = normalize_term(st.session_state.get(f"name_{cat_key}_{idx}", sc.name)) or core or "concept"
    sc.core_concept = core
    sc.original_term = core
    sc.modifier = normalize_term(st.session_state.get(f"modifier_{cat_key}_{idx}", sc.modifier)) or None
    sc.direction_of_effect = normalize_term(
        st.session_state.get(f"direction_{cat_key}_{idx}", sc.direction_of_effect)
    ) or None
    sc.expanded_terms = split_comma_terms(st.session_state.get(f"terms_{cat_key}_{idx}", ""))


def search_terms_for_subconcept(sc: SubConcept) -> list[str]:
    return sc.expansion_search_terms()


def build_generation_pico(pico: ExtractedPICO) -> tuple[ExtractedPICO, list[dict]]:
    """Apply review selections without mutating the expanded PICO in session state."""
    reviewed = pico.model_copy(deep=True)
    audit_rows: list[dict] = []

    for cat_key in CATEGORY_KEYS:
        for idx, sc in enumerate(getattr(reviewed, cat_key, [])):
            if not st.session_state.get(f"use_mesh_{cat_key}_{idx}", True):
                sc.mesh_descriptor = None

            state_key = f"umls_sel_{cat_key}_{idx}"
            selected_synonyms = st.session_state.get(state_key, sc.umls_synonyms)
            manual_terms = split_comma_terms(st.session_state.get(f"manual_terms_{cat_key}_{idx}", ""))
            sc.umls_synonyms = dedupe_terms([*selected_synonyms, *manual_terms])

            audit_rows.append({
                "category": cat_key,
                "name": sc.name,
                "core_concept": sc.core_concept or sc.original_term,
                "modifier": sc.modifier or "",
                "mesh": sc.mesh_descriptor.name if sc.mesh_descriptor else "",
                "mesh_entry_terms": len(sc.mesh_descriptor.entry_terms) if sc.mesh_descriptor else 0,
                "umls_synonyms": len(sc.umls_synonyms),
                "manual_terms": ", ".join(manual_terms),
            })

    return reviewed, audit_rows

# Initialize clear counter
if "clear_counter" not in st.session_state:
    st.session_state["clear_counter"] = 0

# Research Question Input
st.subheader("Step 1: Enter Research Question")
question = st.text_area(
    "Enter your research question:",
    placeholder="e.g., Does propranolol reduce migraine frequency in children under 12?",
    height=100,
    key=f"research_question_{st.session_state['clear_counter']}"
)

# Action Buttons
col1, col2 = st.columns([3, 1])
with col1:
    extract_btn = st.button("Extract & Analyze Concepts", type="primary", use_container_width=True)
with col2:
    st.button("Clear All", use_container_width=True, on_click=clear_all_callback)

# =============================================================================
# Step 1: Extract Sub-Concepts
# =============================================================================

if extract_btn:
    if not question:
        st.error("Please enter a research question.")
    else:
        clear_downstream_state()
        clear_prefixed_state((
            "name_", "core_", "modifier_", "direction_", "terms_",
            "use_mesh_", "umls_sel_", "manual_terms_", "cui_select_", "show_all_",
        ))
        st.session_state["original_question"] = question
        with st.status("Extracting concepts with LLM...", expanded=True) as status:
            st.write("Sending request to LLM...")
            
            extractor = get_keyword_extractor()
            temp = st.session_state.get("temperature", 0.1)
            top_p = st.session_state.get("top_p", 0.3)
            
            pico = extractor.extract_subconcepts(question, temperature=temp, top_p=top_p)
            st.session_state["extracted_pico"] = pico
            st.session_state["llm_raw_response"] = extractor.last_raw_response
            st.session_state["llm_error"] = extractor.last_error
            st.session_state["llm_used_fallback"] = extractor.used_fallback
            
            # Count sub-concepts
            total = len(pico.all_sub_concepts())
            status.update(label=f"Extracted {total} sub-concepts!", state="complete")
            
        st.success(f"Extracted {total} sub-concepts across PICO categories!")
        if extractor.used_fallback:
            st.warning(extractor.last_error or "LLM extraction was unavailable; manual fallback terms were generated.")

# =============================================================================
# Step 2: Review Sub-Concepts
# =============================================================================

if "extracted_pico" in st.session_state:
    st.divider()
    st.subheader("Step 2: Review & Edit Sub-Concepts")
    
    st.info("""
    Audit the concept structure before expansion. Core concepts are expanded through MeSH/UMLS; modifiers are kept as strict text filters; direction-of-effect terms are recorded for transparency but excluded from query generation.
    """)
    if st.session_state.get("llm_used_fallback"):
        st.warning(st.session_state.get("llm_error") or "LLM extraction used the manual fallback. Review all concepts carefully.")
    elif st.session_state.get("llm_error"):
        st.warning(st.session_state["llm_error"])
    if st.session_state.get("llm_raw_response"):
        with st.expander("LLM raw extraction response", expanded=False):
            st.code(st.session_state["llm_raw_response"], language="json")
    
    pico = st.session_state["extracted_pico"]
    
    categories = [
        ("Population (P)", "population", "Who are the patients/subjects?"),
        ("Intervention (I)", "intervention", "What treatment/exposure is being studied?"),
        ("Comparison (C)", "comparison", "What is it compared to?"),
        ("Outcome (O)", "outcome", "What effects are measured?"),
        ("Other", "other", "Additional search terms"),
    ]
    
    for cat_label, cat_key, cat_desc in categories:
        sub_concepts = getattr(pico, cat_key, [])
        
        with st.expander(f"{cat_label} ({len(sub_concepts)} sub-concepts)", expanded=len(sub_concepts) > 0):
            st.caption(cat_desc)
            
            if not sub_concepts:
                st.write("*No sub-concepts extracted for this category*")
                if st.button(f"Add {cat_label} concept", key=f"add_{cat_key}", on_click=add_subconcept, args=(cat_key,)):
                    st.rerun()
            else:
                # Display each sub-concept
                for idx, sc in enumerate(list(sub_concepts)):
                    with st.container(border=True):
                        col_name, col_core, col_modifier, col_remove = st.columns([1.2, 2.2, 2.2, 0.8], vertical_alignment="center")

                        with col_name:
                            st.text_input(
                                "Label",
                                value=sc.name,
                                key=f"name_{cat_key}_{idx}",
                                on_change=clear_downstream_state,
                            )

                        with col_core:
                            st.text_input(
                                "Core concept",
                                value=sc.core_concept or sc.original_term,
                                key=f"core_{cat_key}_{idx}",
                                help="Expanded through MeSH/UMLS. Keep this as the main medical entity.",
                                on_change=clear_downstream_state,
                            )

                        with col_modifier:
                            st.text_input(
                                "Modifier",
                                value=sc.modifier or "",
                                key=f"modifier_{cat_key}_{idx}",
                                help="Strict text filter. Do not use for vocabulary expansion.",
                                on_change=clear_downstream_state,
                            )

                        with col_remove:
                            st.button(
                                "Remove",
                                key=f"remove_{cat_key}_{idx}",
                                on_click=remove_subconcept,
                                args=(cat_key, idx),
                                use_container_width=True,
                            )

                        col_terms, col_direction = st.columns([3, 1.4], vertical_alignment="top")
                        with col_terms:
                            st.text_input(
                                "Known synonyms, abbreviations, exact wording, brand names",
                                value=", ".join(sc.expanded_terms),
                                key=f"terms_{cat_key}_{idx}",
                                help="These terms are also sent to MeSH/UMLS and remain auditable later.",
                                on_change=clear_downstream_state,
                            )
                        with col_direction:
                            st.text_input(
                                "Direction recorded, not searched",
                                value=sc.direction_of_effect or "",
                                key=f"direction_{cat_key}_{idx}",
                                help="Examples: reduction, prevention, increase. Excluded to avoid direction bias.",
                                on_change=clear_downstream_state,
                            )

                        sync_subconcept_from_inputs(sc, cat_key, idx)
                        if sc.explanation:
                            st.caption(sc.explanation)

                if st.button(f"Add {cat_label} concept", key=f"add_{cat_key}", on_click=add_subconcept, args=(cat_key,)):
                    st.rerun()

                # Logic preview
                if sub_concepts:
                    st.markdown("---")
                    st.markdown("**Query logic preview for this category:**")
                    logic_parts = []
                    for sc in sub_concepts:
                        all_terms = search_terms_for_subconcept(sc)[:3]
                        modifier = f" AND {sc.modifier}" if sc.modifier else ""
                        logic_parts.append(f"({' OR '.join(all_terms)}...){modifier}")
                    st.code(" AND ".join(logic_parts), language=None)
    
    st.divider()
    
    # ==========================================================================
    # Step 3: Expand Terms
    # ==========================================================================
    
    expand_btn = st.button(
        "Step 3: Expand with MeSH & UMLS", 
        type="primary", 
        use_container_width=True,
        help="Look up each term in MeSH and UMLS databases to find additional synonyms"
    )
    
    if expand_btn:
        data_source = st.session_state.get("data_source", DataSource.LOCAL)
        settings = get_search_settings()
        
        if data_source == DataSource.API:
            # ===== API Mode =====
            umls_api_key = get_umls_api_key()
            if not umls_api_key:
                st.error("UMLS API key required. Please enter it in the sidebar.")
            else:
                with st.status("Searching UMLS API...", expanded=True) as status:
                    pico = st.session_state["extracted_pico"].model_copy(deep=True)
                    
                    # Initialize UMLS client
                    rate_limiter = RateLimiter(max_requests=19)
                    umls_client = UMLSClient(api_key=umls_api_key, rate_limiter=rate_limiter)
                    
                    # Collect terms with sub-concept mapping
                    term_to_subconcept = {}  # term -> (cat_key, sc_index)
                    for cat_key in CATEGORY_KEYS:
                        for sc_idx, sc in enumerate(getattr(pico, cat_key, [])):
                            for term in search_terms_for_subconcept(sc):
                                if term not in term_to_subconcept:
                                    term_to_subconcept[term] = []
                                term_to_subconcept[term].append((cat_key, sc_idx))
                    
                    all_search_terms = dedupe_terms(term_to_subconcept.keys())
                    st.write(f"Searching {len(all_search_terms)} terms...")
                    
                    # Search all terms and collect CUI candidates with sub-concept links
                    all_cui_candidates = {}
                    for term in all_search_terms:
                        st.write(f"  → Searching: {term}")
                        try:
                            # Use smart search with backoff
                            scored, used_term = umls_client.smart_search(
                                term,
                                min_score=float(settings.min_fuzzy_score),
                                max_results=200,
                            )
                            if used_term != term:
                                st.caption(f"    ↳ Matched via: '{used_term}'")
                            
                            for r in scored[:10]:  # Top 10 per term
                                if r.score < settings.min_fuzzy_score:
                                    continue
                                if r.cui not in all_cui_candidates:
                                    all_cui_candidates[r.cui] = {
                                        "cui": r.cui,
                                        "name": r.name,
                                        "score": r.score,
                                        "sources": [r.root_source] if r.root_source else [],
                                        "matched_terms": [term],
                                        "used_terms": [used_term],
                                        "subconcepts": term_to_subconcept[term].copy(),
                                    }
                                else:
                                    # Boost score and merge sub-concept links
                                    all_cui_candidates[r.cui]["score"] += r.score * 0.5
                                    if r.root_source and r.root_source not in all_cui_candidates[r.cui]["sources"]:
                                        all_cui_candidates[r.cui]["sources"].append(r.root_source)
                                    if term not in all_cui_candidates[r.cui]["matched_terms"]:
                                        all_cui_candidates[r.cui]["matched_terms"].append(term)
                                    if used_term not in all_cui_candidates[r.cui]["used_terms"]:
                                        all_cui_candidates[r.cui]["used_terms"].append(used_term)
                                    for sc_link in term_to_subconcept[term]:
                                        if sc_link not in all_cui_candidates[r.cui]["subconcepts"]:
                                            all_cui_candidates[r.cui]["subconcepts"].append(sc_link)
                        except Exception as e:
                            st.warning(f"Search error for '{term}': {e}")
                    
                    status.update(label=f"Found {len(all_cui_candidates)} unique CUIs", state="complete")
                    
                    # Store candidates for CUI selection step
                    st.session_state["cui_candidates"] = all_cui_candidates
                    st.session_state["api_search_pico"] = pico
                    st.session_state["umls_client"] = umls_client
                    st.session_state["api_search_done"] = True
                    st.session_state["expansion_done"] = False  # Need CUI selection first
        else:
            # ===== Local Mode =====
            with st.status("Expanding terms against MeSH and UMLS...", expanded=True) as status:
                # Load databases
                st.write("Loading MeSH database...")
                try:
                    mesh_loader = get_mesh_loader()
                except FileNotFoundError as e:
                    st.error(str(e))
                    st.stop()
                
                umls_loader = None
                if UMLS_PARQUET_PATH.exists():
                    st.write("Loading UMLS database...")
                    umls_loader = get_umls_loader()
                    if umls_loader:
                        umls_loader.load()
                
                # Expand each sub-concept
                pico = st.session_state["extracted_pico"].model_copy(deep=True)
                total_expanded = 0
                
                for cat_key in CATEGORY_KEYS:
                    sub_concepts = getattr(pico, cat_key, [])
                    
                    for sc in sub_concepts:
                        search_terms = search_terms_for_subconcept(sc)
                        st.write(f"Expanding: {sc.core_concept or sc.original_term}")
                        
                        # MeSH lookup
                        mesh_desc = None
                        for term in search_terms:
                            mesh_desc = mesh_loader.search_by_name(term)
                            if mesh_desc:
                                break
                        if not mesh_desc:
                            fuzzy_results = []
                            for term in search_terms:
                                fuzzy_results.extend(
                                    mesh_loader.search_fuzzy(
                                        term,
                                        limit=5,
                                        min_score=settings.min_fuzzy_score,
                                    )
                                )
                            mesh_desc = fuzzy_results[0] if fuzzy_results else None
                        
                        if mesh_desc:
                            sc.mesh_descriptor = mesh_desc
                            total_expanded += 1
                        
                        # UMLS lookup
                        if umls_loader:
                            try:
                                synonym_pool = []
                                for term in search_terms:
                                    umls_results = umls_loader.search(
                                        term,
                                        limit=5,
                                        min_score=settings.min_fuzzy_score,
                                    )
                                    for result in umls_results:
                                        synonym_pool.extend(result.synonyms)
                                sc.umls_synonyms = dedupe_terms([*sc.umls_synonyms, *synonym_pool])
                            except Exception as e:
                                st.warning(f"UMLS error for '{sc.core_concept or sc.original_term}': {e}")
                
                st.session_state["expanded_pico"] = pico
                st.session_state["expansion_done"] = True
                st.session_state["api_search_done"] = False
                status.update(label=f"Expansion complete! {total_expanded} MeSH matches found.", state="complete")

# =============================================================================
# Step 3b: CUI Selection (API Mode Only)
# =============================================================================

if st.session_state.get("api_search_done", False) and not st.session_state.get("expansion_done", False):
    st.divider()
    st.subheader("Step 3b: Select Concepts for Expansion")
    
    cui_candidates = st.session_state.get("cui_candidates", {})
    
    if cui_candidates:
        st.markdown(f"Found **{len(cui_candidates)}** unique concepts. MeSH terms prioritized. Select which ones to expand:")
        
        # Group CUIs by PICO category
        category_labels = {
            "population": "Population",
            "intervention": "Intervention", 
            "comparison": "Comparison",
            "outcome": "Outcome",
            "other": "Other"
        }
        
        category_cuis = {cat: [] for cat in category_labels}
        
        for cui, data in cui_candidates.items():
            # Find which categories this CUI belongs to
            cats_for_cui = set()
            for cat_key, sc_idx in data.get("subconcepts", []):
                cats_for_cui.add(cat_key)
            
            # Add to each category it belongs to
            for cat in cats_for_cui:
                category_cuis[cat].append(data)
        
        # Sort each category: MeSH first, then by score
        for cat in category_cuis:
            category_cuis[cat] = sorted(
                category_cuis[cat], 
                key=lambda x: (
                    0 if 'MSH' in x.get('sources', []) else 1,  # MeSH first
                    -x["score"]  # Then by score descending
                )
            )
        
        # Track total pre-selected count
        total_preselected = 0
        max_preselect = 20
        
        # Display per-category tabs
        selected_cuis = []
        
        for cat_key, cat_label in category_labels.items():
            cuis_in_cat = category_cuis[cat_key]
            if not cuis_in_cat:
                continue
            
            with st.expander(f"{cat_label} ({len(cuis_in_cat)} concepts)", expanded=True):
                # Determine how many to show
                show_all_key = f"show_all_{cat_key}"
                show_all = st.session_state.get(show_all_key, False)
                display_limit = len(cuis_in_cat) if show_all else min(20, len(cuis_in_cat))
                
                for i, cui_data in enumerate(cuis_in_cat[:display_limit]):
                    # Determine if should be pre-selected (up to 20 total)
                    should_preselect = total_preselected < max_preselect and i < 20
                    
                    # Build source/relation tag
                    sources = cui_data.get('sources', [])
                    source_tag = "[MSH]" if 'MSH' in sources else (f"[{sources[0]}]" if sources else "")
                    
                    col1, col2, col3 = st.columns([5, 2, 1])
                    with col1:
                        if st.checkbox(
                            f"**{cui_data['name']}** ({cui_data['cui']})",
                            value=should_preselect,
                            key=f"cui_select_{cat_key}_{cui_data['cui']}"
                        ):
                            if cui_data["cui"] not in selected_cuis:
                                selected_cuis.append(cui_data["cui"])
                            if should_preselect and i < 20:
                                total_preselected += 1
                    with col2:
                        st.caption(source_tag)
                    with col3:
                        st.caption(f"{cui_data['score']:.0f}")
                    st.caption(
                        "Matched: "
                        + ", ".join(cui_data.get("matched_terms", [])[:4])
                    )
                
                # Show more button if there are more than 20
                remaining = len(cuis_in_cat) - 20
                if remaining > 0 and not show_all:
                    if st.button(f"Show {remaining} more...", key=f"show_more_{cat_key}"):
                        st.session_state[show_all_key] = True
                        st.rerun()
        
        # Expand selected CUIs button
        if st.button("Expand Selected Concepts", type="primary", disabled=not selected_cuis):
            umls_client = st.session_state.get("umls_client")
            pico = st.session_state.get("api_search_pico", st.session_state["extracted_pico"]).model_copy(deep=True)
            
            with st.status("Expanding selected concepts...", expanded=True) as status:
                # Track per-subconcept expansions
                subconcept_mesh = {}  # (cat_key, idx) -> list of mesh terms
                subconcept_umls = {}  # (cat_key, idx) -> list of umls synonyms
                global_mesh_backbone = []
                
                for cui in selected_cuis:
                    cui_data = cui_candidates[cui]
                    cui_name = cui_data["name"]
                    sc_links = cui_data.get("subconcepts", [])
                    
                    st.write(f"Expanding: {cui_name} ({cui})")
                    
                    try:
                        # Get atoms
                        atoms = umls_client.get_atoms(cui)
                        atom_classification = umls_client.classify_atoms(atoms)
                        
                        # Get relations
                        relations = umls_client.get_relations(cui)
                        rel_classification = umls_client.classify_relations(relations)
                        
                        # Combine MeSH backbone
                        mesh_terms = atom_classification["mesh_backbone"] + rel_classification["mesh_backbone"]
                        free_terms = atom_classification["free_text"] + rel_classification["free_text"]
                        
                        global_mesh_backbone.extend(mesh_terms)
                        
                        # Assign to originating sub-concepts
                        for sc_link in sc_links:
                            if sc_link not in subconcept_mesh:
                                subconcept_mesh[sc_link] = []
                                subconcept_umls[sc_link] = []
                            subconcept_mesh[sc_link].extend(mesh_terms)
                            subconcept_umls[sc_link].extend(free_terms)
                        
                    except Exception as e:
                        st.warning(f"Error expanding {cui}: {e}")
                
                # Apply to PICO sub-concepts
                for cat_key in CATEGORY_KEYS:
                    sub_concepts = getattr(pico, cat_key, [])
                    for sc_idx, sc in enumerate(sub_concepts):
                        sc_link = (cat_key, sc_idx)
                        
                        # Assign MeSH terms (create a simple MeSHDescriptor if we have backbone terms)
                        if sc_link in subconcept_mesh and subconcept_mesh[sc_link]:
                            mesh_terms = dedupe_terms(subconcept_mesh[sc_link])
                            # Store MeSH backbone as a descriptor-like object
                            if not sc.mesh_descriptor:
                                sc.mesh_descriptor = MeSHDescriptor(
                                    ui="API:UMLS",
                                    name=mesh_terms[0] if mesh_terms else "",
                                    entry_terms=mesh_terms[1:] if len(mesh_terms) > 1 else [],
                                    tree_numbers=[],
                                    qualifiers=[]
                                )
                            else:
                                sc.mesh_descriptor.entry_terms = dedupe_terms([*sc.mesh_descriptor.entry_terms, *mesh_terms])
                        
                        # Assign UMLS synonyms
                        if sc_link in subconcept_umls:
                            sc.umls_synonyms.extend(subconcept_umls[sc_link])
                            sc.umls_synonyms = dedupe_terms(sc.umls_synonyms)
                
                # Deduplicate global
                global_mesh_backbone = dedupe_terms(global_mesh_backbone)
                
                st.session_state["expanded_pico"] = pico
                st.session_state["mesh_backbone_terms"] = global_mesh_backbone
                st.session_state["expansion_done"] = True
                
                status.update(
                    label=f"Done! Terms assigned to {len(subconcept_mesh)} sub-concepts",
                    state="complete"
                )

# =============================================================================
# Step 4: Review Expanded Terms & Generate Queries
# =============================================================================

if st.session_state.get("expansion_done", False):
    st.divider()
    st.subheader("Step 4: Review Expanded Terms")
    
    pico = st.session_state.get("expanded_pico", st.session_state.get("extracted_pico"))
    settings = get_search_settings()
    
    for cat_key in CATEGORY_KEYS:
        sub_concepts = getattr(pico, cat_key, [])
        if not sub_concepts:
            continue
        
        st.markdown(f"### {cat_key.capitalize()}")
        
        for idx, sc in enumerate(sub_concepts):
            title = sc.core_concept or sc.original_term
            with st.expander(f"**{sc.name}**: {title}", expanded=True):
                if sc.modifier:
                    st.caption(f"Modifier will be ANDed as text: {sc.modifier}")
                if sc.direction_of_effect:
                    st.caption(f"Direction recorded but excluded: {sc.direction_of_effect}")
                col_mesh, col_umls = st.columns(2)
                
                with col_mesh:
                    st.markdown("**MeSH**")
                    if sc.mesh_descriptor:
                        st.checkbox(
                            f"Include: {sc.mesh_descriptor.name}",
                            value=True,
                            key=f"use_mesh_{cat_key}_{idx}"
                        )
                        entry_count = len(sc.mesh_descriptor.entry_terms)
                        st.caption(f"+ {entry_count} controlled/entry terms")
                    else:
                        st.caption("No MeSH match found")
                
                with col_umls:
                    st.markdown("**UMLS Synonyms**")
                    if sc.umls_synonyms:
                        # Already filtered to English at API level
                        state_key = f"umls_sel_{cat_key}_{idx}"
                        
                        default_synonyms = sc.umls_synonyms if state_key not in st.session_state else None
                        st.multiselect(
                            "Select synonyms:",
                            options=sc.umls_synonyms,
                            default=default_synonyms,
                            key=state_key,
                            label_visibility="collapsed"
                        )
                    else:
                        st.caption("No UMLS synonyms found")
                    st.text_input(
                        "Manual additional terms",
                        key=f"manual_terms_{cat_key}_{idx}",
                        placeholder="Comma-separated terms to include after audit",
                        help="Added directly to the final free-text synonym set.",
                    )
    
    st.divider()
    
    # Generate Queries Button
    if st.button("Step 5: Generate Final Queries", type="primary", use_container_width=True):
        settings = get_search_settings()
        builder = QueryBuilder(settings=settings)
        
        generation_pico, audit_rows = build_generation_pico(pico)
        
        queries = []
        for db in selected_dbs:
            query = builder.build_pico_query(generation_pico, db)
            queries.append(query)
        
        st.session_state["queries"] = queries
        st.session_state["query_audit_rows"] = audit_rows
        st.session_state["query_question"] = st.session_state.get("original_question", question)
        st.success(f"Generated queries for {len(queries)} databases!")

# =============================================================================
# Display Results
# =============================================================================

if "queries" in st.session_state:
    st.divider()
    queries = st.session_state["queries"]
    query_question = st.session_state.get("query_question", st.session_state.get("original_question", question))
    
    # Download All Queries
    download_text = f"Search Queries Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    download_text += f"Question: {query_question}\n\n"
    download_text += "=" * 80 + "\n\n"
    
    db_names = {
        Database.PUBMED: "PubMed",
        Database.EMBASE: "Embase",
        Database.COCHRANE: "Cochrane Library",
        Database.WEB_OF_SCIENCE: "Web of Science",
        Database.SCOPUS: "Scopus",
        Database.SEMANTIC_SCHOLAR: "Semantic Scholar"
    }
    
    for query in queries:
        db_name = db_names[query.database]
        download_text += f"DATABASE: {db_name}\n"
        download_text += "-" * 40 + "\n"
        download_text += f"{query.query_string}\n\n"
        download_text += "=" * 80 + "\n\n"
    
    st.download_button(
        label="Download All Queries (TXT)",
        data=download_text,
        file_name=f"search_queries_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
        mime="text/plain",
        type="primary"
    )
    
    st.divider()
    st.subheader("Generated Search Queries")
    if st.session_state.get("query_audit_rows"):
        with st.expander("Final term audit summary", expanded=False):
            st.dataframe(st.session_state["query_audit_rows"], use_container_width=True)
    
    for query in queries:
        db_name = db_names[query.database]
        
        with st.expander(f"{db_name}", expanded=True):
            st.code(query.query_string, language=None)
            # Note: st.code() has a built-in copy button in the top-right corner

# =============================================================================
# Footer
# =============================================================================

st.divider()
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.9em;">
    MeSH Search Query Tool • Built with Streamlit<br>
    Using UMLS and MeSH databases for comprehensive term expansion<br>
    <strong>Sub-concept query logic: (terms OR'd) AND (sub-concepts AND'd) AND (categories AND'd)</strong>
</div>
""", unsafe_allow_html=True)
