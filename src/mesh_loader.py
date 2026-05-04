"""MeSH descriptor loader using lxml for efficient XML parsing."""

from pathlib import Path
from typing import Callable, Dict, List, Optional, Iterator
from lxml import etree

from .models import MeSHDescriptor, MeSHQualifier
from .term_utils import dedupe_terms, normalize_term


class MeSHLoader:
    """Loader for MeSH descriptor XML data."""
    
    def __init__(self, xml_path: Optional[Path] = None):
        """
        Initialize the MeSH loader.
        
        Args:
            xml_path: Path to desc20XX.xml file
        """
        self.xml_path = xml_path
        self._descriptors: Optional[Dict[str, MeSHDescriptor]] = None
        self._name_index: Optional[Dict[str, str]] = None  # term -> UI
        self._tree_index: Optional[Dict[str, List[str]]] = None  # tree_number -> [UIs]
    
    def _parse_descriptor(self, elem: etree._Element) -> MeSHDescriptor:
        """Parse a single DescriptorRecord element."""
        ui = elem.findtext("DescriptorUI", "")
        name = elem.findtext("DescriptorName/String", "")
        
        # Get tree numbers
        tree_numbers = [
            tn.text for tn in elem.findall(".//TreeNumber") 
            if tn.text
        ]
        
        # Get entry terms (synonyms)
        entry_terms = []
        for concept in elem.findall(".//Concept"):
            for term in concept.findall(".//Term"):
                term_string = term.findtext("String", "")
                if term_string and term_string != name:
                    entry_terms.append(term_string)
        
        # Get allowable qualifiers
        qualifiers = []
        for qual in elem.findall(".//AllowableQualifier"):
            qual_ui = qual.findtext("QualifierReferredTo/QualifierUI", "")
            qual_name = qual.findtext("QualifierReferredTo/QualifierName/String", "")
            abbrev = qual.findtext("Abbreviation", "")
            if qual_ui and qual_name:
                qualifiers.append(MeSHQualifier(
                    ui=qual_ui,
                    name=qual_name,
                    abbreviation=abbrev
                ))
        
        return MeSHDescriptor(
            ui=ui,
            name=name,
            entry_terms=dedupe_terms(entry_terms),
            tree_numbers=tree_numbers,
            qualifiers=qualifiers
        )
    
    def _iter_descriptors(self) -> Iterator[MeSHDescriptor]:
        """Stream-parse the XML file to yield descriptors."""
        if not self.xml_path or not self.xml_path.exists():
            raise FileNotFoundError(f"MeSH XML not found at {self.xml_path}")
        
        # Use iterparse for memory efficiency
        context = etree.iterparse(
            str(self.xml_path), 
            events=("end",), 
            tag="DescriptorRecord",
            no_network=True,
            resolve_entities=False,
        )
        
        for event, elem in context:
            yield self._parse_descriptor(elem)
            # Clear element to free memory
            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]
    
    def load(self, progress_callback: Optional[Callable[[str], None]] = None) -> Dict[str, MeSHDescriptor]:
        """Load all descriptors into memory."""
        if self._descriptors is not None:
            return self._descriptors
        
        def log(msg: str):
            print(msg)
            if progress_callback:
                progress_callback(msg)

        log(f"Loading MeSH descriptors from {self.xml_path}...")
        self._descriptors = {}
        
        count = 0
        for desc in self._iter_descriptors():
            self._descriptors[desc.ui] = desc
            count += 1
            if count % 5000 == 0:
                log(f"  Loaded {count:,} descriptors...")
        
        log(f"Total: {len(self._descriptors):,} MeSH descriptors loaded")
        return self._descriptors
    
    def build_name_index(self) -> Dict[str, str]:
        """Build an inverted index from term names to descriptor UIs."""
        if self._name_index is not None:
            return self._name_index
        
        descriptors = self.load()
        self._name_index = {}
        
        for ui, desc in descriptors.items():
            # Index the preferred name
            self._name_index[normalize_term(desc.name).casefold()] = ui
            
            # Index all entry terms
            for term in desc.entry_terms:
                term_lower = normalize_term(term).casefold()
                # Don't overwrite if already exists (prefer earlier matches)
                if term_lower not in self._name_index:
                    self._name_index[term_lower] = ui
        
        print(f"Built name index with {len(self._name_index):,} terms")
        return self._name_index
    
    def build_tree_index(self) -> Dict[str, List[str]]:
        """Build an index from tree numbers to descriptor UIs."""
        if self._tree_index is not None:
            return self._tree_index
        
        descriptors = self.load()
        self._tree_index = {}
        
        for ui, desc in descriptors.items():
            for tree_num in desc.tree_numbers:
                if tree_num not in self._tree_index:
                    self._tree_index[tree_num] = []
                self._tree_index[tree_num].append(ui)
        
        return self._tree_index
    
    def search_by_name(self, term: str) -> Optional[MeSHDescriptor]:
        """
        Exact match search by term name (case-insensitive).
        O(1) lookup using inverted index.
        """
        name_index = self.build_name_index()
        ui = name_index.get(normalize_term(term).casefold())
        
        if ui:
            return self._descriptors.get(ui)
        return None
    
    def search_fuzzy(
        self, 
        term: str, 
        limit: Optional[int] = None,  # None = no limit
        min_score: int = 80
    ) -> List[MeSHDescriptor]:
        """Fuzzy search for MeSH terms. Returns all matches above min_score."""
        from rapidfuzz import fuzz, process
        
        name_index = self.build_name_index()
        all_terms = list(name_index.keys())
        
        matches = process.extract(
            term.lower(),
            all_terms,
            scorer=fuzz.WRatio,
            limit=limit
        )
        
        results = []
        seen_uis = set()
        
        for matched_term, score, _ in matches:
            if score < min_score:
                continue
            ui = name_index[matched_term]
            if ui not in seen_uis:
                seen_uis.add(ui)
                desc = self._descriptors.get(ui)
                if desc:
                    results.append(desc)
        
        return results
    
    def get_children(self, descriptor: MeSHDescriptor) -> List[MeSHDescriptor]:
        """
        Get all child descriptors (for tree explosion).
        Children are those whose tree numbers start with this descriptor's tree numbers.
        """
        tree_index = self.build_tree_index()
        descriptors = self.load()
        
        children_uis = set()
        
        for tree_num in descriptor.tree_numbers:
            # Find all tree numbers that start with this one
            for tn, uis in tree_index.items():
                if tn.startswith(tree_num + ".") and tn != tree_num:
                    children_uis.update(uis)
        
        return [
            descriptors[ui] for ui in children_uis 
            if ui in descriptors
        ]
    
    def get_by_ui(self, ui: str) -> Optional[MeSHDescriptor]:
        """Get a descriptor by its UI."""
        descriptors = self.load()
        return descriptors.get(ui)


# Singleton instance for caching
_mesh_loader_instance: Optional[MeSHLoader] = None


def get_mesh_loader(xml_path: Optional[Path] = None) -> MeSHLoader:
    """Get or create a cached MeSH loader instance."""
    global _mesh_loader_instance
    
    if _mesh_loader_instance is None:
        if xml_path is None:
            # Default path
            xml_path = Path(__file__).parent.parent / "META" / "desc2026.xml"
        _mesh_loader_instance = MeSHLoader(xml_path)
    
    return _mesh_loader_instance


if __name__ == "__main__":
    import sys
    
    # Default path
    xml_path = Path(__file__).parent.parent / "META" / "desc2026.xml"
    
    if len(sys.argv) > 1:
        xml_path = Path(sys.argv[1])
    
    print("MeSH Loader Test")
    print("=" * 50)
    
    loader = MeSHLoader(xml_path)
    loader.load()
    loader.build_name_index()
    
    # Test search
    test_terms = ["vitamin c", "diabetes", "heart failure"]
    for term in test_terms:
        result = loader.search_by_name(term)
        if result:
            print(f"\n'{term}' -> {result.name} ({result.ui})")
            print(f"  Entry terms: {result.entry_terms[:3]}...")
        else:
            # Try fuzzy
            results = loader.search_fuzzy(term, limit=3)
            print(f"\n'{term}' (fuzzy) -> {[r.name for r in results]}")
