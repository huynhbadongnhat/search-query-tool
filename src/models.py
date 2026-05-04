"""Pydantic models for MeSH Search Query Tool."""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict
from enum import Enum

from .term_utils import dedupe_terms, normalize_term


class Database(str, Enum):
    """Supported database targets."""
    PUBMED = "pubmed"
    EMBASE = "embase"
    COCHRANE = "cochrane"
    WEB_OF_SCIENCE = "wos"
    SCOPUS = "scopus"
    SEMANTIC_SCHOLAR = "semantic_scholar"


class DataSource(str, Enum):
    """Data source for term expansion."""
    LOCAL = "local"  # Local files (META/ directory)
    API = "api"      # UMLS REST API


# =============================================================================
# Search Settings (Detailed Options)
# =============================================================================

class SearchSettings(BaseModel):
    """Detailed search sensitivity settings."""
    
    # MeSH Settings
    include_mesh_preferred: bool = Field(
        default=True,
        description="Include MeSH preferred terms (main headings). These are the official, standardized terms in the MeSH hierarchy."
    )
    include_mesh_entry_terms: bool = Field(
        default=True,
        description="Include MeSH entry terms (synonyms). These are alternative terms that map to the preferred term."
    )
    explode_mesh_tree: bool = Field(
        default=False,
        description="Explode MeSH tree to include narrower/child terms. This broadens the search but may reduce precision."
    )
    
    # UMLS Settings
    include_umls_synonyms: bool = Field(
        default=True,
        description="Include synonyms from UMLS (Unified Medical Language System). Provides comprehensive term coverage across vocabularies."
    )
    
    # Match Quality
    min_fuzzy_score: int = Field(
        default=90,
        ge=50,
        le=100,
        description="Minimum fuzzy match score (50-100). Higher values = stricter matching, fewer false positives."
    )
    
    # Text Search Settings
    include_title_abstract: bool = Field(
        default=True,
        description="Search in title and abstract fields. Essential for comprehensive literature search."
    )
    
    # Proximity Search (PubMed feature)
    proximity_distance: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Word distance for proximity search [Title/Abstract:~N]. 0=disabled, 1-5=allow N words between terms."
    )

    @classmethod
    def high_sensitivity(cls) -> "SearchSettings":
        """Preset for high sensitivity (broad search)."""
        return cls(
            include_mesh_preferred=True,
            include_mesh_entry_terms=True,
            explode_mesh_tree=True,
            include_umls_synonyms=True,
            min_fuzzy_score=70,
            include_title_abstract=True
        )
    
    @classmethod
    def balanced(cls) -> "SearchSettings":
        """Preset for balanced search."""
        return cls(
            include_mesh_preferred=True,
            include_mesh_entry_terms=True,
            explode_mesh_tree=False,
            include_umls_synonyms=True,
            min_fuzzy_score=80,
            include_title_abstract=True
        )
    
    @classmethod
    def high_precision(cls) -> "SearchSettings":
        """Preset for high precision (narrow search)."""
        return cls(
            include_mesh_preferred=True,
            include_mesh_entry_terms=False,
            explode_mesh_tree=False,
            include_umls_synonyms=False,
            min_fuzzy_score=90,
            include_title_abstract=True
        )


# =============================================================================
# UMLS Models
# =============================================================================

class UMLSMetadata(BaseModel):
    """Metadata for a UMLS term entry."""
    cui: str  # Concept Unique Identifier
    source: str  # e.g., MSH, SNOMEDCT_US
    code: str  # Source-specific code


class UMLSTermResult(BaseModel):
    """Result from UMLS lookup."""
    cui: str
    preferred_name: str
    synonyms: List[str] = Field(default_factory=list)
    metadata: List[UMLSMetadata] = Field(default_factory=list)


# =============================================================================
# MeSH Models
# =============================================================================

class MeSHQualifier(BaseModel):
    """MeSH subheading/qualifier."""
    ui: str  # Qualifier UI (Q...)
    name: str  # e.g., "therapy"
    abbreviation: str  # e.g., "TH"


class MeSHDescriptor(BaseModel):
    """MeSH descriptor (main heading)."""
    ui: str  # Descriptor UI (D...)
    name: str  # Preferred name
    entry_terms: List[str] = Field(default_factory=list)  # Synonyms from XML
    tree_numbers: List[str] = Field(default_factory=list)  # For hierarchy/explosion
    qualifiers: List[MeSHQualifier] = Field(default_factory=list)


# =============================================================================
# Sub-Concept Models (NEW)
# =============================================================================

class SubConcept(BaseModel):
    """
    A sub-concept within a PICO category with semantic decomposition.
    
    The key insight: separate expandable CORE concepts from TEXT-ONLY modifiers.
    
    - core_concept: Main medical entity → EXPAND via UMLS (e.g., "Thyroid Eye Disease")
    - modifier: Constraining adjective → TEXT-ONLY search, no UMLS (e.g., "active", "acute")
    - direction_of_effect: Outcome direction → DISCARDED to avoid bias (e.g., "reduction")
    
    This prevents searching for "Active Thyroid Eye Disease" as a phrase (fails in UMLS)
    and instead constructs: (TED synonyms...) AND (active[tiab])
    """
    name: str  # Descriptive name for the sub-concept
    
    # NEW: Semantic decomposition
    core_concept: str = ""  # The main entity to expand via UMLS
    modifier: Optional[str] = None  # Constraining adjective (text-only, no UMLS expansion)
    direction_of_effect: Optional[str] = None  # Outcome direction (DISCARDED to avoid bias)
    explanation: Optional[str] = None  # LLM reasoning
    
    # LEGACY: Keep for backward compatibility during transition
    original_term: str = ""  # Will be deprecated, use core_concept
    expanded_terms: List[str] = Field(default_factory=list)  # LLM/manual synonyms
    
    # Expansion results
    mesh_descriptor: Optional[MeSHDescriptor] = None
    umls_synonyms: List[str] = Field(default_factory=list)

    @field_validator("name", "core_concept", "original_term", mode="before")
    @classmethod
    def _normalize_required_text(cls, value: str | None) -> str:
        return normalize_term(value)

    @field_validator("modifier", "direction_of_effect", "explanation", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        normalized = normalize_term(value)
        return normalized or None

    @field_validator("expanded_terms", "umls_synonyms", mode="before")
    @classmethod
    def _dedupe_term_lists(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        return dedupe_terms(value)

    def model_post_init(self, __context) -> None:
        """Keep the legacy original_term populated while core_concept is adopted."""
        if not self.core_concept and self.original_term:
            self.core_concept = self.original_term
        if self.core_concept and not self.original_term:
            self.original_term = self.core_concept
    
    def get_all_terms(self, settings: SearchSettings) -> List[str]:
        """Get all terms for this sub-concept based on settings."""
        terms = [self.core_concept or self.original_term]
        terms.extend(self.expanded_terms)
        
        if self.mesh_descriptor:
            if settings.include_mesh_preferred:
                terms.append(self.mesh_descriptor.name)
            if settings.include_mesh_entry_terms:
                terms.extend(self.mesh_descriptor.entry_terms)
        
        if settings.include_umls_synonyms:
            terms.extend(self.umls_synonyms)
        
        return dedupe_terms(terms)

    def expansion_search_terms(self) -> List[str]:
        """Terms that should be sent to MeSH/UMLS for expansion.

        Modifiers are intentionally excluded because they are strict text filters,
        not vocabulary-expansion targets.
        """
        return dedupe_terms([self.core_concept or self.original_term, *self.expanded_terms])


class PICOCategory(BaseModel):
    """
    A PICO category containing sub-concepts.
    
    Sub-concepts are AND'd together.
    Terms within each sub-concept are OR'd together.
    """
    category: str  # population, intervention, comparison, outcome, other
    sub_concepts: List[SubConcept] = Field(default_factory=list)
    
    def is_empty(self) -> bool:
        """Check if this category has any sub-concepts."""
        return len(self.sub_concepts) == 0


class ExtractedPICO(BaseModel):
    """
    Complete PICO extraction with sub-concepts.
    
    This is the output from the LLM keyword extraction.
    """
    population: List[SubConcept] = Field(default_factory=list)
    intervention: List[SubConcept] = Field(default_factory=list)
    comparison: List[SubConcept] = Field(default_factory=list)
    outcome: List[SubConcept] = Field(default_factory=list)
    other: List[SubConcept] = Field(default_factory=list)
    
    def get_category(self, name: str) -> List[SubConcept]:
        """Get sub-concepts for a category by name."""
        return getattr(self, name, [])
    
    def set_category(self, name: str, sub_concepts: List[SubConcept]):
        """Set sub-concepts for a category."""
        setattr(self, name, sub_concepts)
    
    def all_sub_concepts(self) -> List[SubConcept]:
        """Get all sub-concepts across all categories."""
        return (
            self.population + 
            self.intervention + 
            self.comparison + 
            self.outcome + 
            self.other
        )


# =============================================================================
# Legacy Models (for backwards compatibility)
# =============================================================================

class Sensitivity(str, Enum):
    """Search sensitivity levels (legacy - use SearchSettings instead)."""
    HIGH = "high"
    BALANCED = "balanced"
    PRECISE = "precise"


class ConceptTerms(BaseModel):
    """Terms for a single concept after expansion (legacy)."""
    original_keyword: str
    mesh_descriptor: Optional[MeSHDescriptor] = None
    umls_synonyms: List[str] = Field(default_factory=list)
    
    def get_all_terms(self, sensitivity: Sensitivity) -> List[str]:
        """Get all terms based on sensitivity level."""
        terms = [self.original_keyword]
        
        if self.mesh_descriptor:
            terms.append(self.mesh_descriptor.name)
            if sensitivity in [Sensitivity.HIGH, Sensitivity.BALANCED]:
                terms.extend(self.mesh_descriptor.entry_terms)
        
        if sensitivity in [Sensitivity.HIGH, Sensitivity.BALANCED]:
            terms.extend(self.umls_synonyms)
        
        return dedupe_terms(terms)
    
    @classmethod
    def from_sub_concept(cls, sub: SubConcept) -> "ConceptTerms":
        """Convert a SubConcept to legacy ConceptTerms."""
        return cls(
            original_keyword=sub.original_term,
            mesh_descriptor=sub.mesh_descriptor,
            umls_synonyms=sub.umls_synonyms
        )


# =============================================================================
# Search Result Models
# =============================================================================

class SearchQuery(BaseModel):
    """Generated search query for a database."""
    database: Database
    query_string: str
    concepts: List[ConceptTerms] = Field(default_factory=list)  # Legacy
    pico: Optional[ExtractedPICO] = None  # New sub-concept structure


class SearchResult(BaseModel):
    """Complete search result with queries for all databases."""
    original_question: str
    keywords: List[str]
    concepts: List[ConceptTerms]  # Legacy
    queries: List[SearchQuery]

