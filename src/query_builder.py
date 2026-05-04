"""Multi-database query builder with syntax adapters."""

from typing import List, Optional, Union, Dict
from abc import ABC, abstractmethod

from .models import (
    Database, Sensitivity, ConceptTerms, SearchQuery, 
    MeSHDescriptor, SubConcept, ExtractedPICO, SearchSettings
)
from .term_utils import dedupe_terms, is_likely_query_term, normalize_term


class DatabaseAdapter(ABC):
    """Abstract base class for database-specific query syntax."""
    
    database: Database
    quote_char = '"'
    reserved_words = {"AND", "OR", "NOT"}

    def __init__(self, include_title_abstract: bool = True):
        self.include_title_abstract = include_title_abstract
    
    @abstractmethod
    def format_mesh_term(self, term: str, explode: bool = False) -> str:
        """Format a MeSH/controlled vocabulary term."""
        pass
    
    @abstractmethod
    def format_text_term(self, term: str) -> str:
        """Format a free-text term for title/abstract search."""
        pass
    
    @abstractmethod
    def combine_or(self, terms: List[str]) -> str:
        """Combine terms with OR operator."""
        pass
    
    @abstractmethod
    def combine_and(self, blocks: List[str]) -> str:
        """Combine blocks with AND operator."""
        pass
    
    def quote_if_needed(self, term: str) -> str:
        """Normalize, escape, and quote terms when database syntax needs it."""
        term = normalize_term(term)
        term = normalize_term(self.escape_term(term))
        needs_quote = (
            " " in term
            or term.upper() in self.reserved_words
            or any(char in term for char in [":", "[", "]", "(", ")"])
        )
        if needs_quote:
            return f"{self.quote_char}{term}{self.quote_char}"
        return term

    def escape_term(self, term: str) -> str:
        """Escape quote characters without introducing field syntax."""
        if self.quote_char == "'":
            return term.replace("'", "''")
        return term.replace('"', " ")


class PubMedAdapter(DatabaseAdapter):
    """PubMed query syntax adapter."""
    
    database = Database.PUBMED
    
    def __init__(
        self,
        proximity_distance: int = 0,
        include_title_abstract: bool = True,
    ):
        """
        Initialize PubMed adapter.
        
        Args:
            proximity_distance: Word distance for proximity search (0-5).
                               0 = words must be adjacent (any order)
                               1-5 = allow N words between terms
        """
        super().__init__(include_title_abstract=include_title_abstract)
        self.proximity_distance = proximity_distance
    
    def format_mesh_term(self, term: str, explode: bool = False) -> str:
        quoted = self.quote_if_needed(term)
        if explode:
            return f"{quoted}[MeSH Terms]"
        return f"{quoted}[MeSH Terms:noexp]"
    
    def format_text_term(self, term: str) -> str:
        quoted = self.quote_if_needed(term)
        # Use proximity search ONLY for multi-word phrases (2+ words)
        # Correct syntax is [Title/Abstract:~N]
        # Single words MUST use [tiab] - proximity on single words is invalid!
        words = term.strip().split()
        if not self.include_title_abstract:
            return quoted
        if len(words) >= 2 and self.proximity_distance > 0:
            return f"{quoted}[Title/Abstract:~{self.proximity_distance}]"
        return f"{quoted}[tiab]"
    
    def combine_or(self, terms: List[str]) -> str:
        if not terms:
            return ""
        if len(terms) == 1:
            return terms[0]
        return "(" + " OR ".join(terms) + ")"
    
    def combine_and(self, blocks: List[str]) -> str:
        blocks = [b for b in blocks if b]
        if not blocks:
            return ""
        if len(blocks) == 1:
            return blocks[0]
        return " AND ".join(blocks)


class EmbaseAdapter(DatabaseAdapter):
    """Embase query syntax adapter."""
    
    database = Database.EMBASE
    quote_char = "'"
    
    def format_mesh_term(self, term: str, explode: bool = False) -> str:
        # Embase uses single quotes around descriptors
        term = self.escape_term(normalize_term(term))
        if explode:
            return f"'{term}'/exp"
        return f"'{term}'/de"  # de = descriptor, no explosion
    
    def format_text_term(self, term: str) -> str:
        quoted = self.quote_if_needed(term)
        if not self.include_title_abstract:
            return quoted
        return f"{quoted}:ti,ab"
    
    def combine_or(self, terms: List[str]) -> str:
        if not terms:
            return ""
        if len(terms) == 1:
            return terms[0]
        return "(" + " OR ".join(terms) + ")"
    
    def combine_and(self, blocks: List[str]) -> str:
        blocks = [b for b in blocks if b]
        if not blocks:
            return ""
        if len(blocks) == 1:
            return blocks[0]
        return " AND ".join(blocks)


class CochraneAdapter(DatabaseAdapter):
    """Cochrane Library query syntax adapter."""
    
    database = Database.COCHRANE
    
    def format_mesh_term(self, term: str, explode: bool = False) -> str:
        # Cochrane uses MeSH through the interface
        term = normalize_term(term).replace("[", " ").replace("]", " ")
        if explode:
            return f"[mh {term}]"
        return f"[mh ^{term}]"  # ^ = no explosion
    
    def format_text_term(self, term: str) -> str:
        quoted = self.quote_if_needed(term)
        if not self.include_title_abstract:
            return quoted
        return f"{quoted}:ti,ab,kw"
    
    def combine_or(self, terms: List[str]) -> str:
        if not terms:
            return ""
        if len(terms) == 1:
            return terms[0]
        return "(" + " OR ".join(terms) + ")"
    
    def combine_and(self, blocks: List[str]) -> str:
        blocks = [b for b in blocks if b]
        if not blocks:
            return ""
        if len(blocks) == 1:
            return blocks[0]
        return " AND ".join(blocks)


class WebOfScienceAdapter(DatabaseAdapter):
    """Web of Science query syntax adapter."""
    
    database = Database.WEB_OF_SCIENCE
    
    def format_mesh_term(self, term: str, explode: bool = False) -> str:
        # WoS doesn't have MeSH, treat as topic search
        return self.format_text_term(term)
    
    def format_text_term(self, term: str) -> str:
        quoted = self.quote_if_needed(term)
        field = "TS" if self.include_title_abstract else "ALL"
        return f"{field}={quoted}"
    
    def combine_or(self, terms: List[str]) -> str:
        if not terms:
            return ""
        if len(terms) == 1:
            return terms[0]
        return "(" + " OR ".join(terms) + ")"
    
    def combine_and(self, blocks: List[str]) -> str:
        blocks = [b for b in blocks if b]
        if not blocks:
            return ""
        if len(blocks) == 1:
            return blocks[0]
        return " AND ".join(blocks)


class ScopusAdapter(DatabaseAdapter):
    """Scopus query syntax adapter."""
    
    database = Database.SCOPUS
    
    def format_mesh_term(self, term: str, explode: bool = False) -> str:
        # Scopus doesn't have MeSH, treat as keyword search
        return self.format_text_term(term)
    
    def format_text_term(self, term: str) -> str:
        quoted = self.quote_if_needed(term)
        if not self.include_title_abstract:
            return f"ALL({quoted})"
        return f"TITLE-ABS-KEY({quoted})"
    
    def combine_or(self, terms: List[str]) -> str:
        if not terms:
            return ""
        if len(terms) == 1:
            return terms[0]
        return "(" + " OR ".join(terms) + ")"
    
    def combine_and(self, blocks: List[str]) -> str:
        blocks = [b for b in blocks if b]
        if not blocks:
            return ""
        if len(blocks) == 1:
            return blocks[0]
        return " AND ".join(blocks)


class SemanticScholarAdapter(DatabaseAdapter):
    """Semantic Scholar API query adapter.
    
    Uses the /paper/search relevance search endpoint which takes a plain-text
    query string. The API handles semantic matching internally, so we only
    need to provide the core concept keywords from the PICO framework.
    """
    
    database = Database.SEMANTIC_SCHOLAR
    
    def format_mesh_term(self, term: str, explode: bool = False) -> str:
        # Semantic Scholar uses simple text - just return the term
        return term
    
    def format_text_term(self, term: str) -> str:
        # Return term as-is for relevance search
        return term
    
    def combine_or(self, terms: List[str]) -> str:
        # For S2 relevance search, we don't need all synonyms
        # Just use the first (most important) term
        if not terms:
            return ""
        return terms[0]  # Return only the primary term
    
    def combine_and(self, blocks: List[str]) -> str:
        blocks = [b for b in blocks if b]
        if not blocks:
            return ""
        # Join main concept terms with spaces for relevance search
        return " ".join(blocks)


ADAPTER_CLASSES = {
    Database.EMBASE: EmbaseAdapter,
    Database.COCHRANE: CochraneAdapter,
    Database.WEB_OF_SCIENCE: WebOfScienceAdapter,
    Database.SCOPUS: ScopusAdapter,
    Database.SEMANTIC_SCHOLAR: SemanticScholarAdapter,
}


class QueryBuilder:
    """Build search queries for multiple databases."""
    
    def __init__(
        self, 
        settings: Optional[SearchSettings] = None,
        sensitivity: Optional[Sensitivity] = None  # Legacy
    ):
        """
        Initialize the query builder.
        
        Args:
            settings: Detailed search settings (preferred)
            sensitivity: Legacy sensitivity level
        """
        if settings:
            self.settings = settings
        elif sensitivity:
            # Convert legacy sensitivity to settings
            if sensitivity == Sensitivity.HIGH:
                self.settings = SearchSettings.high_sensitivity()
            elif sensitivity == Sensitivity.PRECISE:
                self.settings = SearchSettings.high_precision()
            else:
                self.settings = SearchSettings.balanced()
        else:
            self.settings = SearchSettings.balanced()
        
        # Keep legacy for backwards compatibility
        self.sensitivity = sensitivity or Sensitivity.BALANCED
        
        # Create adapters cache (some need settings)
        self._adapters = {}
    
    def get_adapter(self, database: Database) -> DatabaseAdapter:
        """Get adapter for a database, creating with settings if needed."""
        if database not in self._adapters:
            if database == Database.PUBMED:
                # PubMed needs proximity distance from settings
                self._adapters[database] = PubMedAdapter(
                    proximity_distance=self.settings.proximity_distance,
                    include_title_abstract=self.settings.include_title_abstract,
                )
            else:
                self._adapters[database] = ADAPTER_CLASSES[database](
                    include_title_abstract=self.settings.include_title_abstract
                )
        return self._adapters[database]
    
    def build_subconcept_block(
        self,
        sub_concept: SubConcept,
        adapter: DatabaseAdapter
    ) -> str:
        """
        Build a query block for a single sub-concept using semantic decomposition.
        
        Strategy (NEW):
        - core_concept → EXPAND via UMLS/MeSH → OR'd together
        - modifier → TEXT-ONLY [tiab] → AND with expanded core
        - direction_of_effect → DISCARDED (to avoid outcome bias)
        
        Returns:
            Query string like: ((core_terms...) AND modifier[tiab])
            or just (core_terms...) if no modifier
        """
        mesh_terms = []  # Terms to be formatted as controlled vocabulary
        text_terms = []  # Terms to be formatted as free text [tiab]
        
        # Get the core term (prefer core_concept, fall back to original_term)
        core_term = sub_concept.core_concept or sub_concept.original_term
        
        # ---------------------------------------------------------------------
        # 1. Core concept + expanded terms → [tiab]
        # ---------------------------------------------------------------------
        if core_term:
            text_terms.append(core_term)
        text_terms.extend(sub_concept.expanded_terms)
        
        # ---------------------------------------------------------------------
        # 2. MeSH terms (for databases that support controlled vocabulary)
        # ---------------------------------------------------------------------
        if sub_concept.mesh_descriptor and adapter.database in [
            Database.PUBMED, Database.EMBASE, Database.COCHRANE
        ]:
            # MeSH preferred term → [MeSH] (controlled vocabulary indexing)
            if self.settings.include_mesh_preferred:
                mesh_terms.append(sub_concept.mesh_descriptor.name)
            
            # MeSH entry terms → [tiab] (these are synonyms, NOT indexed as MeSH)
            # They help find articles that use different terminology
            if self.settings.include_mesh_entry_terms:
                if sub_concept.mesh_descriptor.ui.startswith("API:"):
                    mesh_terms.extend(sub_concept.mesh_descriptor.entry_terms)
                else:
                    text_terms.extend(sub_concept.mesh_descriptor.entry_terms)
        
        # ---------------------------------------------------------------------
        # 3. UMLS synonyms → [tiab] (free text from other vocabularies)
        # ---------------------------------------------------------------------
        if self.settings.include_umls_synonyms:
            text_terms.extend(sub_concept.umls_synonyms)
        
        # ---------------------------------------------------------------------
        # 4. Format all terms with appropriate tags
        # ---------------------------------------------------------------------
        formatted_terms = []
        
        # Helper: Sanitize terms (remove noise)
        def clean_term(term: str) -> str:
            """Clean up a term."""
            return normalize_term(term)
        
        # Add MeSH terms with controlled vocabulary tagging
        for mesh_term in mesh_terms:
            mesh_term = clean_term(mesh_term)
            if not is_likely_query_term(
                mesh_term,
                english_only=self.settings.english_only_terms,
            ):
                continue
            formatted = adapter.format_mesh_term(
                mesh_term,
                explode=self.settings.explode_mesh_tree
            )
            formatted_terms.append(formatted)
        
        # Add text terms with [tiab] tagging
        for text_term in text_terms:
            text_term = clean_term(text_term)
            if not is_likely_query_term(
                text_term,
                english_only=self.settings.english_only_terms,
            ):
                continue
            formatted = adapter.format_text_term(text_term)
            formatted_terms.append(formatted)
        
        # ---------------------------------------------------------------------
        # 5. Remove duplicates while preserving order
        # ---------------------------------------------------------------------
        unique_terms = dedupe_terms(formatted_terms, max_length=500)
        
        # Build the core concepts block (OR'd)
        core_block = adapter.combine_or(unique_terms)
        
        # ---------------------------------------------------------------------
        # 6. Handle modifier (text-only, ANDed with core)
        # Note: direction_of_effect is explicitly DISCARDED to avoid outcome bias
        # ---------------------------------------------------------------------
        if sub_concept.modifier and core_block:
            modifier = normalize_term(sub_concept.modifier)
            if not is_likely_query_term(
                modifier,
                english_only=self.settings.english_only_terms,
            ):
                return core_block
            modifier_term = adapter.format_text_term(modifier)
            # AND the modifier with the core concepts
            return f"({core_block} AND {modifier_term})"
        
        return core_block
    
    def build_pico_query(
        self,
        pico: ExtractedPICO,
        database: Database
    ) -> SearchQuery:
        """
        Build a query from ExtractedPICO with proper AND/OR logic.
        
        Logic for most databases:
        - Terms within a sub-concept: OR
        - Sub-concepts within a category: AND
        - Categories: AND
        
        For Semantic Scholar:
        - Uses only original concept keywords (API handles semantic matching)
        """
        adapter = self.get_adapter(database)
        
        # Special handling for Semantic Scholar - simple keyword query
        if database == Database.SEMANTIC_SCHOLAR:
            return self._build_semantic_scholar_query(pico)
        
        category_blocks = []
        
        # Process each PICO category
        for category in ["population", "intervention", "comparison", "outcome", "other"]:
            sub_concepts = getattr(pico, category, [])
            if not sub_concepts:
                continue
            
            # Build block for each sub-concept (will be AND'd together)
            sub_concept_blocks = []
            for sc in sub_concepts:
                block = self.build_subconcept_block(sc, adapter)
                if block:
                    sub_concept_blocks.append(block)
            
            if sub_concept_blocks:
                # AND sub-concepts within category
                category_query = adapter.combine_and(sub_concept_blocks)
                # Wrap in parens if multiple sub-concepts
                if len(sub_concept_blocks) > 1:
                    category_query = f"({category_query})"
                category_blocks.append(category_query)
        
        # AND categories together
        query_string = adapter.combine_and(category_blocks)
        
        return SearchQuery(
            database=database,
            query_string=query_string,
            pico=pico
        )
    
    def _build_semantic_scholar_query(self, pico: ExtractedPICO) -> SearchQuery:
        """
        Build a Semantic Scholar query using only original concept keywords.
        
        The S2 relevance search API handles semantic matching internally,
        so we only need to provide the core PICO concept terms.
        """
        concept_keywords = []
        
        for category in ["population", "intervention", "comparison", "outcome", "other"]:
            sub_concepts = getattr(pico, category, [])
            for sc in sub_concepts:
                # Only use the original term (single word best for relevance matching)
                keyword = sc.core_concept or sc.original_term
                if keyword:
                    concept_keywords.append(keyword)
                if sc.modifier:
                    concept_keywords.append(sc.modifier)
        
        # Join all concept keywords with spaces for relevance search
        query_string = " ".join(
            dedupe_terms(
                concept_keywords,
                english_only=self.settings.english_only_terms,
            )
        )
        
        return SearchQuery(
            database=Database.SEMANTIC_SCHOLAR,
            query_string=query_string,
            pico=pico
        )
    
    # =========================================================================
    # Legacy Methods
    # =========================================================================
    
    def build_concept_block(
        self, 
        concept: Union[ConceptTerms, str],
        adapter: DatabaseAdapter,
        include_explosion: bool = False
    ) -> str:
        """Build a query block for a single concept (legacy)."""
        # Defensive check: if concept is a string, wrap it
        if isinstance(concept, str):
            print(f"Warning: Strings passed to build_concept_block: {concept}")
            concept = ConceptTerms(original_keyword=concept)
            
        terms = []
        
        # Add MeSH term if available (for MeSH-supporting databases)
        if concept.mesh_descriptor and adapter.database in [
            Database.PUBMED, Database.EMBASE, Database.COCHRANE
        ]:
            mesh_term = adapter.format_mesh_term(
                concept.mesh_descriptor.name,
                explode=include_explosion
            )
            terms.append(mesh_term)
            
            # Add entry terms as text for high/balanced sensitivity
            if self.sensitivity in [Sensitivity.HIGH, Sensitivity.BALANCED]:
                for entry in concept.mesh_descriptor.entry_terms:
                    terms.append(adapter.format_text_term(entry))
        
        # Add UMLS synonyms for high/balanced
        if self.sensitivity in [Sensitivity.HIGH, Sensitivity.BALANCED]:
            for syn in concept.umls_synonyms:
                terms.append(adapter.format_text_term(syn))
        
        # Always add original keyword
        terms.append(adapter.format_text_term(concept.original_keyword))
        
        # Remove duplicates
        unique_terms = dedupe_terms(terms, max_length=500)
        
        return adapter.combine_or(unique_terms)
    
    def build_query(
        self, 
        concepts: Union[List[ConceptTerms], Dict[str, List[ConceptTerms]]],
        database: Database
    ) -> SearchQuery:
        """
        Build a complete query for a database (legacy method).
        
        Args:
            concepts: List of concept terms OR Dict of PICO categories -> lists
            database: Target database
            
        Returns:
            SearchQuery with formatted query string
        """
        adapter = self.get_adapter(database)
        include_explosion = self.sensitivity == Sensitivity.HIGH
        
        if isinstance(concepts, list):
            # Legacy behavior: flatten and AND everything
            blocks = []
            for concept in concepts:
                block = self.build_concept_block(
                    concept, adapter, include_explosion
                )
                if block:
                    blocks.append(block)
            query_string = adapter.combine_and(blocks)
            flat_concepts = concepts
            
        elif isinstance(concepts, dict):
            # PICO Structured Query: (P1 OR P2) AND (I1 OR I2) AND ...
            pico_blocks = []
            flat_concepts = []
            
            # Process in logical order: P, I, C, O, Other
            order = ["population", "intervention", "comparison", "outcome", "other"]
            
            for category in order:
                cat_concepts = concepts.get(category, [])
                if not cat_concepts:
                    continue
                
                # Build OR block for this category
                cat_term_blocks = []
                for concept in cat_concepts:
                    flat_concepts.append(concept)
                    block = self.build_concept_block(
                        concept, adapter, include_explosion
                    )
                    if block:
                        cat_term_blocks.append(block)
                
                # OR terms within category, then wrap in parens
                if cat_term_blocks:
                    # Combine with OR
                    category_query = adapter.combine_or(cat_term_blocks)
                    if len(cat_term_blocks) > 1:
                        category_query = f"({category_query})"
                    pico_blocks.append(category_query)
            
            # Combine categories with AND
            query_string = adapter.combine_and(pico_blocks)
            
        else:
            raise ValueError("concepts must be List or Dict")
        
        return SearchQuery(
            database=database,
            query_string=query_string,
            concepts=flat_concepts
        )
    
    def build_all_queries(
        self, 
        concepts: List[ConceptTerms]
    ) -> List[SearchQuery]:
        """Build queries for all supported databases (legacy)."""
        return [
            self.build_query(concepts, db)
            for db in Database
        ]
    
    def build_all_pico_queries(
        self,
        pico: ExtractedPICO
    ) -> List[SearchQuery]:
        """Build queries for all supported databases using PICO sub-concepts."""
        return [
            self.build_pico_query(pico, db)
            for db in Database
        ]
