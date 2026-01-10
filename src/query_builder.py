"""Multi-database query builder with syntax adapters."""

from typing import List, Optional, Union, Dict
from abc import ABC, abstractmethod

from .models import (
    Database, Sensitivity, ConceptTerms, SearchQuery, 
    MeSHDescriptor, SubConcept, ExtractedPICO, SearchSettings
)


class DatabaseAdapter(ABC):
    """Abstract base class for database-specific query syntax."""
    
    database: Database
    
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
        """Quote multi-word terms."""
        if ' ' in term:
            return f'"{term}"'
        return term


class PubMedAdapter(DatabaseAdapter):
    """PubMed query syntax adapter."""
    
    database = Database.PUBMED
    
    def __init__(self, proximity_distance: int = 0):
        """
        Initialize PubMed adapter.
        
        Args:
            proximity_distance: Word distance for proximity search (0-5).
                               0 = words must be adjacent (any order)
                               1-5 = allow N words between terms
        """
        self.proximity_distance = proximity_distance
    
    def format_mesh_term(self, term: str, explode: bool = False) -> str:
        quoted = self.quote_if_needed(term)
        if explode:
            return f"{quoted}[MeSH]"
        return f"{quoted}[MeSH:NoExp]"
    
    def format_text_term(self, term: str) -> str:
        quoted = self.quote_if_needed(term)
        # Use proximity search for multi-word phrases when enabled (PubMed feature)
        # Only add ~N syntax when proximity_distance > 0
        if ' ' in term and self.proximity_distance > 0:
            return f"{quoted}[tiab:~{self.proximity_distance}]"
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
    
    def format_mesh_term(self, term: str, explode: bool = False) -> str:
        # Embase uses single quotes around descriptors
        if explode:
            return f"'{term}'/exp"
        return f"'{term}'/de"  # de = descriptor, no explosion
    
    def format_text_term(self, term: str) -> str:
        quoted = self.quote_if_needed(term)
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
        if explode:
            return f"[mh {term}]"
        return f"[mh ^{term}]"  # ^ = no explosion
    
    def format_text_term(self, term: str) -> str:
        quoted = self.quote_if_needed(term)
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
        return f"TS={quoted}"
    
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


# Adapter registry (for non-PubMed that don't need settings)
DEFAULT_ADAPTERS = {
    Database.EMBASE: EmbaseAdapter(),
    Database.COCHRANE: CochraneAdapter(),
    Database.WEB_OF_SCIENCE: WebOfScienceAdapter(),
    Database.SCOPUS: ScopusAdapter(),
    Database.SEMANTIC_SCHOLAR: SemanticScholarAdapter(),
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
                    proximity_distance=self.settings.proximity_distance
                )
            else:
                self._adapters[database] = DEFAULT_ADAPTERS[database]
        return self._adapters[database]
    
    def build_subconcept_block(
        self,
        sub_concept: SubConcept,
        adapter: DatabaseAdapter
    ) -> str:
        """
        Build a query block for a single sub-concept.
        All terms within a sub-concept are OR'd together.
        
        Term tagging strategy:
        - MeSH preferred term → [MeSH] or [MeSH:NoExp] (controlled vocabulary)
        - MeSH entry terms → [tiab] (free text - these are synonyms, not indexed as MeSH)
        - UMLS synonyms → [tiab] (free text)
        - Original/expanded terms → [tiab] (free text)
        
        Returns:
            Query string like: (MeSH_term[MeSH] OR synonym1[tiab] OR synonym2[tiab])
        """
        mesh_terms = []  # Terms to be formatted as controlled vocabulary
        text_terms = []  # Terms to be formatted as free text [tiab]
        
        # ---------------------------------------------------------------------
        # 1. Free-text terms (original + expanded) → [tiab]
        # ---------------------------------------------------------------------
        text_terms.append(sub_concept.original_term)
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
        
        # Add MeSH terms with controlled vocabulary tagging
        for mesh_term in mesh_terms:
            formatted = adapter.format_mesh_term(
                mesh_term,
                explode=self.settings.explode_mesh_tree
            )
            formatted_terms.append(formatted)
        
        # Add text terms with [tiab] tagging
        for text_term in text_terms:
            formatted = adapter.format_text_term(text_term)
            formatted_terms.append(formatted)
        
        # ---------------------------------------------------------------------
        # 5. Remove duplicates while preserving order
        # ---------------------------------------------------------------------
        seen = set()
        unique_terms = []
        for t in formatted_terms:
            if t.lower() not in seen:
                seen.add(t.lower())
                unique_terms.append(t)
        
        return adapter.combine_or(unique_terms)
    
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
                if sc.original_term:
                    concept_keywords.append(sc.original_term)
        
        # Join all concept keywords with spaces for relevance search
        query_string = " ".join(concept_keywords)
        
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
        seen = set()
        unique_terms = []
        for t in terms:
            if t.lower() not in seen:
                seen.add(t.lower())
                unique_terms.append(t)
        
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
