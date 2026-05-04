"""UMLS data loader using Polars for efficient processing of MRCONSO.RRF."""

import polars as pl
from pathlib import Path
from typing import Callable, List, Optional
from rapidfuzz import fuzz, process

from .models import UMLSTermResult, UMLSMetadata
from .term_utils import dedupe_terms, normalize_term


# MRCONSO.RRF column schema (0-indexed)
# CUI|LAT|TS|LUI|STT|SUI|ISPREF|AUI|SAUI|SCUI|SDUI|SAB|TTY|CODE|STR|...
MRCONSO_COLUMNS = [
    "CUI", "LAT", "TS", "LUI", "STT", "SUI", "ISPREF", 
    "AUI", "SAUI", "SCUI", "SDUI", "SAB", "TTY", "CODE", "STR",
    "SRL", "SUPPRESS", "CVF"
]

# Columns we actually need
REQUIRED_COLUMNS = ["CUI", "LAT", "SAB", "TTY", "CODE", "STR", "ISPREF", "SUPPRESS"]

# Default sources to include
DEFAULT_SOURCES = ["MSH", "SNOMEDCT_US", "NCI", "RXNORM"]


class UMLSLoader:
    """Loader for UMLS MRCONSO.RRF data."""
    
    def __init__(
        self, 
        rrf_path: Optional[Path] = None,
        parquet_path: Optional[Path] = None,
        sources: Optional[List[str]] = None
    ):
        """
        Initialize the UMLS loader.
        
        Args:
            rrf_path: Path to MRCONSO.RRF file
            parquet_path: Path to preprocessed parquet file
            sources: List of vocabulary sources to include
        """
        self.rrf_path = rrf_path
        self.parquet_path = parquet_path
        self.sources = sources or DEFAULT_SOURCES
        self._df: Optional[pl.DataFrame] = None
        self._term_index: Optional[dict] = None
    
    def preprocess_rrf_to_parquet(
        self,
        output_path: Path,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Path:
        """
        Convert MRCONSO.RRF to filtered Parquet file.
        
        This significantly reduces file size and improves load times.
        """
        def log(msg: str):
            print(msg)
            if progress_callback:
                progress_callback(msg)

        if not self.rrf_path or not self.rrf_path.exists():
            raise FileNotFoundError(f"MRCONSO.RRF not found at {self.rrf_path}")
        
        log(f"Reading MRCONSO.RRF from {self.rrf_path}...")
        log("This may take several minutes for the full file...")
        
        # Read RRF file with proper schema
        # MRCONSO.RRF uses | as separator and has no quotes around fields
        # Some fields contain non-ASCII text and unescaped quotes
        # Use explicit schema to force all columns as strings
        schema_overrides = {col: pl.Utf8 for col in MRCONSO_COLUMNS}
        
        df = pl.read_csv(
            self.rrf_path,
            separator="|",
            has_header=False,
            new_columns=MRCONSO_COLUMNS,
            truncate_ragged_lines=True,
            ignore_errors=True,
            quote_char=None,  # Disable quote parsing - RRF has no quoted fields
            encoding="utf8-lossy",
            schema_overrides=schema_overrides,
            try_parse_dates=False,
        )
        
        log(f"Total rows loaded: {len(df):,}")
        
        log("Filtering English terms and selected sources...")
        # Filter: English only AND specific sources
        filtered = df.filter(
            (pl.col("LAT") == "ENG") & 
            (pl.col("SAB").is_in(self.sources)) &
            (pl.col("SUPPRESS") == "N")
        ).select(REQUIRED_COLUMNS)
        
        log(f"Filtered rows (English, selected sources): {len(filtered):,}")
        
        log(f"Writing parquet to {output_path}...")
        # Write to parquet
        output_path.parent.mkdir(parents=True, exist_ok=True)
        filtered.write_parquet(output_path)
        log(f"Saved filtered data to {output_path}")
        
        self.parquet_path = output_path
        return output_path
    
    def load(self) -> pl.DataFrame:
        """Load the UMLS data from parquet (preferred) or RRF."""
        if self._df is not None:
            return self._df
        
        if self.parquet_path and self.parquet_path.exists():
            print(f"Loading from parquet: {self.parquet_path}")
            self._df = pl.read_parquet(self.parquet_path)
        elif self.rrf_path and self.rrf_path.exists():
            print(f"Loading from RRF: {self.rrf_path}")
            df = pl.read_csv(
                self.rrf_path,
                separator="|",
                has_header=False,
                new_columns=MRCONSO_COLUMNS,
                truncate_ragged_lines=True,
                ignore_errors=True,
                quote_char=None,  # Disable quote parsing
                encoding="utf8-lossy",
                infer_schema_length=0,
            )
            self._df = df.filter(
                (pl.col("LAT") == "ENG") & 
                (pl.col("SAB").is_in(self.sources)) &
                (pl.col("SUPPRESS") == "N")
            ).select(REQUIRED_COLUMNS)
        else:
            raise FileNotFoundError("No UMLS data source available")

        # Backward compatibility for parquet files generated by older versions.
        for column in REQUIRED_COLUMNS:
            if column not in self._df.columns:
                self._df = self._df.with_columns(pl.lit("").alias(column))
        self._df = self._df.select(REQUIRED_COLUMNS)
        
        print(f"Loaded {len(self._df):,} UMLS terms")
        return self._df
    
    def _build_term_index(self) -> dict:
        """Build an index for fast term lookup."""
        if self._term_index is not None:
            return self._term_index
        
        df = self.load()
        self._term_index = {}
        
        # Group by CUI to get all terms for each concept
        for row in df.iter_rows(named=True):
            cui = row["CUI"]
            term = normalize_term(row["STR"])
            source = row["SAB"]
            code = row["CODE"]
            
            if cui not in self._term_index:
                self._term_index[cui] = {
                    "terms": set(),
                    "metadata": []
                }
            
            if term:
                self._term_index[cui]["terms"].add(term)
            self._term_index[cui]["metadata"].append({
                "source": source,
                "code": code
            })
        
        return self._term_index
    
    def search(
        self, 
        query: str, 
        limit: Optional[int] = None,  # None = no limit on CUIs
        min_score: int = 90  # Higher threshold for relevance
    ) -> List[UMLSTermResult]:
        """
        Search for UMLS concepts and return their synonyms.
        
        Strategy: Find CUI by exact/fuzzy match, then get ALL synonyms for that CUI.
        This ensures synonyms are actually related to the query concept.
        
        Args:
            query: Search term
            limit: Maximum number of CUIs to return
            min_score: Minimum fuzzy match score (0-100)
            
        Returns:
            List of UMLSTermResult objects with true synonyms
        """
        df = self.load()
        
        # Step 1: Try exact match first (case-insensitive)
        query = normalize_term(query)
        query_lower = query.casefold()
        exact_matches = df.filter(pl.col("STR").str.to_lowercase() == query_lower)
        
        if len(exact_matches) > 0:
            # Found exact match - get CUIs
            cuis = exact_matches.select("CUI").unique().to_series().to_list()
        else:
            # Step 2: Fuzzy match to find the best matching term
            unique_terms = dedupe_terms(df.select("STR").unique().to_series().to_list())
            
            # Use higher score threshold for relevance
            matches = process.extract(
                query, 
                unique_terms, 
                scorer=fuzz.ratio,  # Use stricter ratio instead of WRatio
                limit=20  # Get top matches only
            )
            
            # Filter by high score
            good_matches = [(term, score) for term, score, _ in matches if score >= min_score]
            
            if not good_matches:
                return []
            
            # Get CUIs for best matched terms
            matched_terms = [m[0] for m in good_matches]
            matched_df = df.filter(pl.col("STR").is_in(matched_terms))
            cuis = matched_df.select("CUI").unique().to_series().to_list()
        
        # Apply limit to CUIs
        if limit and len(cuis) > limit:
            cuis = cuis[:limit]
        
        # Step 3: Get ALL synonyms for each CUI
        results = []
        for cui in cuis:
            cui_df = df.filter(pl.col("CUI") == cui)
            all_terms = dedupe_terms(cui_df.select("STR").unique().to_series().to_list())
            
            # Get metadata
            metadata = []
            seen_metadata = set()
            for row in cui_df.iter_rows(named=True):
                key = (row["SAB"], row["CODE"])
                if key in seen_metadata:
                    continue
                seen_metadata.add(key)
                metadata.append(
                    UMLSMetadata(
                        cui=cui,
                        source=row["SAB"],
                        code=row["CODE"]
                    )
                )
            
            preferred_terms = (
                cui_df.filter(pl.col("ISPREF") == "Y")
                .select("STR")
                .unique()
                .to_series()
                .to_list()
            )
            preferred_candidates = dedupe_terms(preferred_terms) or all_terms
            if not preferred_candidates:
                continue
            preferred = min(preferred_candidates, key=lambda x: (len(x) < 3, len(x)))
            
            results.append(UMLSTermResult(
                cui=cui,
                preferred_name=preferred,
                synonyms=all_terms,
                metadata=metadata
            ))
        
        return results
    
    def get_synonyms_by_cui(self, cui: str) -> List[str]:
        """Get all synonyms for a given CUI."""
        df = self.load()
        matches = df.filter(pl.col("CUI") == cui)
        return dedupe_terms(matches.select("STR").unique().to_series().to_list())


def preprocess_umls(
    rrf_path: Path,
    output_path: Path,
    sources: Optional[List[str]] = None
) -> Path:
    """
    Standalone function to preprocess MRCONSO.RRF to Parquet.
    
    Usage:
        python -m src.umls_loader
    """
    loader = UMLSLoader(rrf_path=rrf_path, sources=sources)
    return loader.preprocess_rrf_to_parquet(output_path)


if __name__ == "__main__":
    import sys
    
    # Default paths
    base_path = Path(__file__).parent.parent / "META"
    rrf_path = base_path / "MRCONSO.RRF"
    output_path = base_path / "umls_filtered.parquet"
    
    if len(sys.argv) > 1:
        rrf_path = Path(sys.argv[1])
    if len(sys.argv) > 2:
        output_path = Path(sys.argv[2])
    
    print("UMLS Preprocessing Tool")
    print("=" * 50)
    preprocess_umls(rrf_path, output_path)
