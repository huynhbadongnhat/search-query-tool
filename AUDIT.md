# Search Query Tool Audit

This audit focuses on correctness, transparency, and reviewability for systematic-review query generation.

## High-Impact Findings

1. **Silent LLM fallback could hide extraction failure**
   - The app previously fell back to manual keyword extraction without surfacing the failure clearly.
   - Revised: extraction diagnostics are stored and shown, including raw LLM JSON when available.

2. **Preset match thresholds were ignored**
   - The sidebar computed preset fuzzy thresholds but always initialized the slider to `90`.
   - Revised: the slider now reflects the active preset.

3. **Manual and LLM-provided expansion terms were underused**
   - Local MeSH/UMLS expansion searched only `original_term`, so audited synonyms, abbreviations, brand names, and exact phrasing could be missed.
   - Revised: expansion uses `core_concept` plus audited `expanded_terms`; modifiers remain strict text filters.

4. **Review controls mutated source expansion data**
   - Unchecking MeSH in Step 4 set `sc.mesh_descriptor = None` during rendering, making the choice destructive and hard to reverse.
   - Revised: final query generation applies review selections to a deep copy and keeps the expanded PICO intact.

5. **Query syntax terms were not escaped**
   - Quotes, brackets, parentheses, and reserved Boolean words could leak into database query syntax.
   - Revised: database adapters normalize and escape query terms before formatting.

6. **API-mode MeSH backbone terms could be downgraded to free text**
   - Multiple MeSH headings returned from UMLS API were stored as entry terms and then formatted as text synonyms.
   - Revised: API-tagged MeSH descriptors keep additional backbone headings as controlled vocabulary.

7. **Mutable model defaults were used throughout Pydantic models**
   - List defaults such as `[]` are poor practice and can create shared-state bugs outside Pydantic safeguards.
   - Revised: list fields use `Field(default_factory=list)`.

8. **Dynamic Streamlit widget keys could overwrite new extractions**
   - After a new extraction or row deletion, old widget state could be reused for a different concept at the same index.
   - Revised: dynamic widget keys are cleared when the PICO structure changes.

9. **Saved API keys were described as secure when stored as plaintext**
   - Windows `chmod` does not protect the saved files, and the app stored keys in local plaintext.
   - Revised: the UI labels this accurately and recommends environment variables or Streamlit secrets on shared machines.

## Revised Workflow

- Step 2 now lets the user audit and edit label, core concept, modifier, known synonyms, and direction-of-effect.
- Core concepts and audited synonyms are sent to MeSH/UMLS; modifiers are not expanded and are ANDed as text filters.
- Step 4 lets the user select UMLS synonyms, add manual final terms, and include/exclude MeSH without mutating the expanded state.
- Generated queries include a final term audit table with counts and selected manual terms.

## Verification

The following checks pass on this branch:

```powershell
uv run python -m unittest discover -s tests
uv run python -m compileall app.py src tests
git diff --check
```

Recommended manual checks:

```powershell
uv run streamlit run app.py
```

Use at least one real question with known expected PICO structure and compare each generated database query against a librarian-reviewed reference strategy.
