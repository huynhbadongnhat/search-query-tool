"""Pydantic models for MeSH Search Query Tool."""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from enum import Enum


class Database(str, Enum):
    """Supported database targets."""
    PUBMED = "pubmed"
    EMBASE = "embase"
    COCHRANE = "cochrane"
    WEB_OF_SCIENCE = "wos"
    SCOPUS = "scopus"
    SEMANTIC_SCHOLAR = "semantic_scholar"


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
        description="Word distance for proximity search [tiab:~N]. 0=disabled, 1-5=allow N words between terms."
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
    synonyms: List[str]
    metadata: List[UMLSMetadata]


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
    entry_terms: List[str]  # Synonyms from XML
    tree_numbers: List[str]  # For hierarchy/explosion
    qualifiers: List[MeSHQualifier]


# =============================================================================
# Sub-Concept Models (NEW)
# =============================================================================

class SubConcept(BaseModel):
    """
    A sub-concept within a PICO category.
    
    Sub-concepts represent distinct aspects that should be AND'd together.
    Terms within a sub-concept are OR'd together.
    
    Example for "pediatric patients under 12":
    - SubConcept(name="age_group", terms=["child", "pediatric", "children"])
    - SubConcept(name="age_limit", terms=["under 12", "age < 12"])
    
    Query: (child OR pediatric OR children) AND (under 12 OR "age < 12")
    """
    name: str  # Descriptive name for the sub-concept
    original_term: str  # The original extracted term
    expanded_terms: List[str] = []  # Synonyms/related terms after expansion
    mesh_descriptor: Optional[MeSHDescriptor] = None
    umls_synonyms: List[str] = []
    
    def get_all_terms(self, settings: SearchSettings) -> List[str]:
        """Get all terms for this sub-concept based on settings."""
        terms = [self.original_term]
        terms.extend(self.expanded_terms)
        
        if self.mesh_descriptor:
            if settings.include_mesh_preferred:
                terms.append(self.mesh_descriptor.name)
            if settings.include_mesh_entry_terms:
                terms.extend(self.mesh_descriptor.entry_terms)
        
        if settings.include_umls_synonyms:
            terms.extend(self.umls_synonyms)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_terms = []
        for term in terms:
            lower = term.lower()
            if lower not in seen:
                seen.add(lower)
                unique_terms.append(term)
        
        return unique_terms


class PICOCategory(BaseModel):
    """
    A PICO category containing sub-concepts.
    
    Sub-concepts are AND'd together.
    Terms within each sub-concept are OR'd together.
    """
    category: str  # population, intervention, comparison, outcome, other
    sub_concepts: List[SubConcept] = []
    
    def is_empty(self) -> bool:
        """Check if this category has any sub-concepts."""
        return len(self.sub_concepts) == 0


class ExtractedPICO(BaseModel):
    """
    Complete PICO extraction with sub-concepts.
    
    This is the output from the LLM keyword extraction.
    """
    population: List[SubConcept] = []
    intervention: List[SubConcept] = []
    comparison: List[SubConcept] = []
    outcome: List[SubConcept] = []
    other: List[SubConcept] = []
    
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
    umls_synonyms: List[str] = []
    
    def get_all_terms(self, sensitivity: Sensitivity) -> List[str]:
        """Get all terms based on sensitivity level."""
        terms = [self.original_keyword]
        
        if self.mesh_descriptor:
            terms.append(self.mesh_descriptor.name)
            if sensitivity in [Sensitivity.HIGH, Sensitivity.BALANCED]:
                terms.extend(self.mesh_descriptor.entry_terms)
        
        if sensitivity in [Sensitivity.HIGH, Sensitivity.BALANCED]:
            terms.extend(self.umls_synonyms)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_terms = []
        for term in terms:
            lower = term.lower()
            if lower not in seen:
                seen.add(lower)
                unique_terms.append(term)
        
        return unique_terms
    
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
    concepts: List[ConceptTerms] = []  # Legacy
    pico: Optional[ExtractedPICO] = None  # New sub-concept structure


class SearchResult(BaseModel):
    """Complete search result with queries for all databases."""
    original_question: str
    keywords: List[str]
    concepts: List[ConceptTerms]  # Legacy
    queries: List[SearchQuery]

