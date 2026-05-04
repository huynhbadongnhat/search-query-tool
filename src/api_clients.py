"""
UMLS API Client with rate limiting.

Provides access to UMLS REST API for:
- Term search (CUI identification)
- Atom retrieval (synonyms, MeSH terms)
- Relation traversal (hierarchical expansion)
"""

import time
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
import threading
import requests

from .term_utils import dedupe_terms, is_likely_query_term, normalize_term


@dataclass
class RateLimiter:
    """Token bucket rate limiter for API calls."""
    
    max_requests: int = 19  # requests per second
    tokens: float = field(default=19.0, init=False)
    last_refill: float = field(default_factory=time.time, init=False)
    lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    
    def acquire(self):
        """Block until a request token is available."""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_refill
            
            # Refill tokens based on elapsed time
            self.tokens = min(self.max_requests, self.tokens + elapsed * self.max_requests)
            self.last_refill = now
            
            if self.tokens < 1:
                # Wait for next token
                wait_time = (1 - self.tokens) / self.max_requests
                time.sleep(wait_time)
                self.tokens = 1
            
            self.tokens -= 1


@dataclass
class UMLSSearchResult:
    """A single result from UMLS search."""
    cui: str
    name: str
    root_source: str
    uri: str
    score: float = 0.0  # Populated by get_best_cui


@dataclass
class UMLSAtom:
    """An atom (term) from UMLS."""
    aui: str
    name: str
    root_source: str  # SAB (e.g., 'MSH', 'SNOMEDCT_US')
    term_type: str    # TTY (e.g., 'MH', 'NM', 'ET', 'PT')
    code: str


@dataclass
class UMLSRelation:
    """A relation between UMLS concepts."""
    related_cui: str
    related_name: str
    rel: str          # REL (e.g., 'SY', 'CHD', 'RL')
    rela: Optional[str]  # RELA (e.g., 'isa', 'tradename_of')
    root_source: str  # SAB


class UMLSClient:
    """
    Client for UMLS REST API.
    
    API Documentation: https://documentation.uts.nlm.nih.gov/rest/home.html
    """
    
    BASE_URL = "https://uts-ws.nlm.nih.gov"
    
    def __init__(self, api_key: str, rate_limiter: Optional[RateLimiter] = None):
        self.api_key = api_key
        self.rate_limiter = rate_limiter or RateLimiter()
        self.version = "current"
        self.session = requests.Session()
        self.last_trace: List[str] = []
    
    def _request(self, endpoint: str, params: Optional[Dict] = None, max_retries: int = 3) -> Dict:
        """Make a rate-limited API request with retry logic."""
        self.rate_limiter.acquire()
        
        url = f"{self.BASE_URL}{endpoint}"
        params = dict(params or {})
        params["apiKey"] = self.api_key
        
        last_error = None
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, params=params, timeout=30)
                if not response.ok:
                    message = f"UMLS API HTTP {response.status_code}"
                    try:
                        payload = response.json()
                        detail = payload.get("error") or payload.get("message")
                        if detail:
                            message = f"{message}: {detail}"
                    except Exception:
                        pass
                    raise RuntimeError(message)
                return response.json()
            except (requests.RequestException, RuntimeError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                    continue
                raise
        
        raise RuntimeError(f"UMLS API request failed after {max_retries} retries: {last_error}")

    def _paged_results(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        max_pages: int = 5,
    ) -> List[Dict[str, Any]]:
        """Fetch UMLS endpoints that return paginated list results."""
        collected: List[Dict[str, Any]] = []
        params = dict(params or {})

        for page_number in range(1, max_pages + 1):
            page_params = dict(params)
            page_params["pageNumber"] = page_number
            data = self._request(endpoint, page_params)
            results = data.get("result", [])
            if not isinstance(results, list):
                return collected
            collected.extend(results)

            page_count = data.get("pageCount")
            if not page_count or page_number >= int(page_count):
                break

        return collected
    
    def search(self, term: str, max_results: int = 200) -> List[UMLSSearchResult]:
        """
        Search UMLS for concepts matching a term.
        
        Args:
            term: Search string
            max_results: Maximum results to return (API max is 200)
        
        Returns:
            List of search results with CUI, name, and source
        """
        term = normalize_term(term)
        endpoint = f"/rest/search/{self.version}"
        params = {
            "string": term,
            "pageSize": min(max_results, 200),
        }
        
        try:
            data = self._request(endpoint, params)
            results = data.get("result", {}).get("results", [])
            
            return [
                UMLSSearchResult(
                    cui=r["ui"],
                    name=normalize_term(r["name"]),
                    root_source=r.get("rootSource", ""),
                    uri=r.get("uri", ""),
                )
                for r in results
                if r.get("ui") != "NONE"
            ]
        except requests.RequestException as e:
            raise RuntimeError(f"UMLS search failed: {e}")
    
    # Noise words that rarely define the core medical concept
    NOISE_WORDS = {
        'patient', 'patients', 'case', 'cases', 'group', 'groups',
        'subject', 'subjects', 'study', 'studies', 'people', 'person',
        'individual', 'individuals', 'adult', 'adults', 'effect', 'effects',
        'treatment', 'therapy', 'management', 'use', 'using', 'with', 'without'
    }
    
    # Routes of administration and dosage forms that confuse UMLS lookup
    # These should be modifiers, not part of the core drug concept
    ROUTES_AND_FORMS = {
        'intravenous', 'iv', 'oral', 'intramuscular', 'im', 'subcutaneous',
        'topical', 'administration', 'dose', 'dosage', 'injection', 'infusion',
        'tablet', 'capsule', 'sublingual', 'transdermal', 'rectal', 'nasal',
        'inhaled', 'systemic', 'local', 'parenteral', 'enteral'
    }
    
    def smart_search(
        self, 
        term: str, 
        min_score: float = 50.0,
        max_results: int = 200
    ) -> tuple[List[UMLSSearchResult], str]:
        """
        Smart search with backoff: tries exact phrase first, 
        then removes noise words and routes if no high-confidence match.
        
        Args:
            term: Search string
            min_score: Minimum score threshold for a "good" match
            max_results: Maximum results
        
        Returns:
            Tuple of (results, search_term_used)
        """
        term = normalize_term(term)
        self.last_trace = [f"Searching UMLS for '{term}'"]

        # Attempt 1: Full phrase
        results = self.search(term, max_results)
        scored = self.score_search_results(term, results)
        
        # Check if we got a good match
        if scored and scored[0].score >= min_score:
            return scored, term
        
        # Attempt 2: Backoff - remove noise words AND routes of administration
        words = term.split()
        cleaned_words = [
            w for w in words 
            if w.lower() not in self.NOISE_WORDS 
            and w.lower() not in self.ROUTES_AND_FORMS
        ]
        cleaned_term = ' '.join(cleaned_words)
        
        # Only retry if we actually removed something and have content left
        if cleaned_term and cleaned_term != term and len(cleaned_term) > 2:
            self.last_trace.append(f"Backoff search used '{cleaned_term}'")
            results = self.search(cleaned_term, max_results)
            scored = self.score_search_results(cleaned_term, results)
            if scored and scored[0].score >= min_score:
                return scored, cleaned_term
        
        # Attempt 3: Try each word individually if multi-word
        if len(words) > 1:
            for word in words:
                if (word.lower() not in self.NOISE_WORDS 
                    and word.lower() not in self.ROUTES_AND_FORMS 
                    and len(word) > 2):
                    results = self.search(word, max_results)
                    scored = self.score_search_results(word, results)
                    if scored and scored[0].score >= min_score:
                        self.last_trace.append(f"Single-word backoff used '{word}'")
                        return scored, word
        
        # Return whatever we have from the original search
        results = self.search(term, max_results)
        return self.score_search_results(term, results), term
    
    # Term types to exclude (clinical drugs, formulations, etc.)
    EXCLUDED_TERM_TYPES = {
        'SCD',   # Semantic Clinical Drug
        'SCDC',  # Semantic Clinical Drug Component
        'SCDF',  # Semantic Clinical Drug Form
        'SCDG',  # Semantic Clinical Drug Group
        'SBD',   # Semantic Branded Drug
        'SBDC',  # Semantic Branded Drug Component
        'SBDF',  # Semantic Branded Drug Form
        'SBDG',  # Semantic Branded Drug Group
        'GPCK',  # Generic Pack
        'BPCK',  # Branded Pack
        'PSN',   # Prescribable Name
        'DF',    # Dose Form
        'DFG',   # Dose Form Group
        'BN',    # Brand Name (keep for tradenames)
        'PIN',   # Precise Ingredient
    }
    
    def get_atoms(self, cui: str, language: str = "ENG") -> List[UMLSAtom]:
        """
        Get all atoms (terms) for a CUI, filtered to English only.
        
        Args:
            cui: Concept Unique Identifier
            language: Language filter (default ENG for English)
        
        Returns:
            List of atoms with SAB, TTY, name
        """
        # First get the atoms URL from the concept
        concept_endpoint = f"/rest/content/{self.version}/CUI/{cui}"
        
        try:
            concept_data = self._request(concept_endpoint)
            atoms_url = concept_data.get("result", {}).get("atoms", "")
            
            if not atoms_url:
                return []
            
            # Fetch atoms with language filter (English only)
            atoms_endpoint = atoms_url.replace(self.BASE_URL, "")
            params = {
                "pageSize": 200,
                "language": language,  # Filter to English only
            }
            
            results = self._paged_results(atoms_endpoint, params, max_pages=5)
            
            # Filter out clinical drug formulations
            filtered_atoms = []
            for a in results:
                tty = a.get("termType", "")
                # Skip excluded term types
                if tty in self.EXCLUDED_TERM_TYPES:
                    continue
                name = normalize_term(a.get("name", ""))
                if not name:
                    continue
                filtered_atoms.append(
                    UMLSAtom(
                        aui=a.get("ui", ""),
                        name=name,
                        root_source=a.get("rootSource", ""),
                        term_type=tty,
                        code=a.get("code", ""),
                    )
                )
            return filtered_atoms
        except Exception as e:
            raise RuntimeError(f"UMLS get_atoms failed for {cui}: {e}")
    
    def get_relations(self, cui: str) -> List[UMLSRelation]:
        """
        Get relations for a CUI.
        
        Args:
            cui: Concept Unique Identifier
        
        Returns:
            List of relations with REL, RELA, related CUI/name
        """
        endpoint = f"/rest/content/{self.version}/CUI/{cui}/relations"
        params = {"pageSize": 200}
        
        try:
            results = self._paged_results(endpoint, params, max_pages=5)
            
            return [
                UMLSRelation(
                    related_cui=r.get("relatedId", "").split("/")[-1],  # Extract CUI from URI
                    related_name=normalize_term(r.get("relatedIdName", "")),
                    rel=r.get("relationLabel", ""),
                    rela=r.get("additionalRelationLabel", "") or None,
                    root_source=r.get("rootSource", ""),
                )
                for r in results
            ]
        except Exception as e:
            raise RuntimeError(f"UMLS get_relations failed for {cui}: {e}")
    
    def get_source_vocabularies(self, cui: str) -> List[str]:
        """
        Get list of source vocabularies (SABs) for a CUI.
        
        Args:
            cui: Concept Unique Identifier
        
        Returns:
            List of vocabulary abbreviations (e.g., ['MSH', 'SNOMEDCT_US'])
        """
        atoms = self.get_atoms(cui)
        return list(set(a.root_source for a in atoms if a.root_source))
    
    # High-value Term Types (TTY) for medical search
    # These indicate preferred/main terms from authoritative sources
    HIGH_VALUE_TTY = {
        'MH',   # MeSH Main Heading (gold standard)
        'NM',   # MeSH Supplementary Concept Name
        'PT',   # Preferred Term (most sources)
        'FN',   # Full Form of Descriptor
        'SY',   # Designated Synonym
        'PN',   # Primary Name
        'HT',   # Hierarchical Term
        'MTH_PT',  # Metathesaurus Preferred Term
    }
    
    # Medium-value TTY (useful but less authoritative)
    MEDIUM_VALUE_TTY = {
        'SYN',  # Synonym
        'ET',   # Entry Term
        'EP',   # Entry Term (print)
        'AB',   # Abbreviation
        'ACR',  # Acronym
    }
    
    def score_search_results(
        self, 
        user_query: str, 
        results: List[UMLSSearchResult]
    ) -> List[UMLSSearchResult]:
        """
        Score and rank search results using TTY-based semantic scoring.
        
        Prioritizes:
        1. MeSH main headings (MH, NM)
        2. Preferred terms from authoritative sources
        3. Exact/starts-with matches
        4. Source authority (MSH > SNOMEDCT > others)
        
        Avoids:
        - Pure string similarity (fails on acronyms)
        - Length penalty (fails on precise terms)
        
        Args:
            user_query: Original search term
            results: Raw search results
        
        Returns:
            Scored and sorted results (best first)
        """
        scored = []
        query_lower = user_query.lower()
        
        for result in results[:30]:  # Top 30 for more coverage
            score = 0.0
            name_lower = result.name.lower()
            
            # 1. Exact match or starts-with (highest value)
            if name_lower == query_lower:
                score += 100  # Exact match
            elif name_lower.startswith(query_lower) or query_lower.startswith(name_lower):
                score += 70   # Starts-with match
            elif query_lower in name_lower or name_lower in query_lower:
                score += 40   # Substring match
            
            # 2. Source authority (MeSH is gold standard)
            if result.root_source == "MSH":
                score += 50
            elif result.root_source == "SNOMEDCT_US":
                score += 35
            elif result.root_source in ("RXNORM", "NCI"):
                score += 25
            
            # 3. Acronym handling - boost short queries matching long names
            if len(query_lower) <= 5 and len(name_lower) > 10:
                # Could be acronym → expanded form
                words = name_lower.split()
                if len(words) >= 2:
                    initials = ''.join(w[0] for w in words if w)
                    if query_lower == initials:
                        score += 80  # Acronym match!
            
            result.score = score
            scored.append(result)
        
        return sorted(scored, key=lambda x: x.score, reverse=True)
    
    def _is_valid_term(self, term: str, *, english_only: bool = True) -> bool:
        """
        Check if a term is valid for inclusion in search query.
        Filters out empty/noisy terms while retaining valid Unicode medical text.
        """
        term = normalize_term(term)
        if "(" in term or ")" in term:
            return False
        return is_likely_query_term(
            term,
            max_length=120,
            english_only=english_only,
        )
    
    def classify_atoms(
        self,
        atoms: List[UMLSAtom],
        *,
        english_only: bool = True,
    ) -> Dict[str, List[str]]:
        """
        Classify atoms into MeSH backbone and free-text terms.
        
        Returns:
            Dict with 'mesh_backbone' and 'free_text' lists
        """
        mesh_backbone = []
        free_text = []
        
        for atom in atoms:
            # Skip invalid terms
            if not self._is_valid_term(atom.name, english_only=english_only):
                continue
                
            if atom.root_source == "MSH" and atom.term_type in ("MH", "NM"):
                mesh_backbone.append(atom.name)
            elif atom.root_source == "MSH" and atom.term_type == "ET":
                free_text.append(atom.name)
            else:
                free_text.append(atom.name)
        
        return {
            "mesh_backbone": dedupe_terms(mesh_backbone, english_only=english_only),
            "free_text": dedupe_terms(free_text, english_only=english_only),
        }
    
    # High-sensitivity RELA tags for medical search (capture synonyms, spellings, historical names)
    VALUABLE_RELA = {
        # Safety Net - MUST include (exact same concept, different spelling/name)
        'has_british_form', 'british_form_of',           # Oedema/Edema, Tumour/Tumor
        'has_prev_name', 'prev_name_of',                 # Historical names
        'has_consumer_friendly_form', 'consumer_friendly_form_of',  # Patient language
        'has_clinician_form', 'clinician_form_of',       # Technical jargon
        'has_expanded_form', 'expanded_form_of',         # Acronym decoder (TED → Thyroid Eye Disease)
        'has_entry_term', 'entry_term_of',               # MeSH index terms
        'has_alias', 'alias_of',                         # General synonyms
        'same_as',                                        # Explicit identity
        
        # Context - Conditionally useful
        'has_tradename', 'tradename_of',                 # Brand names (Tepezza for teprotumumab)
        'has_permuted_term', 'permuted_term_of',         # Word order variations
        'has_acronym', 'acronym_of',                     # Acronym handling
    }
    
    def classify_relations(
        self,
        relations: List[UMLSRelation],
        *,
        english_only: bool = True,
    ) -> Dict[str, List]:
        """
        Classify relations into MeSH, synonyms, and hierarchy.
        Uses high-sensitivity RELA tags for comprehensive coverage.
        
        Returns:
            Dict with 'mesh_backbone', 'free_text', 'hierarchical' lists
        """
        mesh_backbone = []
        free_text = []
        hierarchical = []
        
        for rel in relations:
            # Skip invalid terms
            if not self._is_valid_term(rel.related_name, english_only=english_only):
                continue
            
            # RL from MeSH → MeSH backbone
            if rel.rel == "RL" and rel.root_source == "MSH":
                mesh_backbone.append(rel.related_name)
            
            # High-value RELA tags → free text (these are semantic synonyms)
            elif rel.rela and rel.rela in self.VALUABLE_RELA:
                free_text.append(rel.related_name)
            
            # Synonyms and similar (REL-based)
            elif rel.rel in ("SY", "RQ", "RL"):
                free_text.append(rel.related_name)
            
            # Hierarchical (children with isa) - for optional expansion
            elif rel.rel in ("CHD", "RN") and rel.rela == "isa":
                hierarchical.append({
                    "cui": rel.related_cui,
                    "name": rel.related_name,
                })
        
        return {
            "mesh_backbone": dedupe_terms(mesh_backbone, english_only=english_only),
            "free_text": dedupe_terms(free_text, english_only=english_only),
            "hierarchical": hierarchical,
        }
