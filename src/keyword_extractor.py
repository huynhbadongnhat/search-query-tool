"""Keyword extractor using NanoGPT API (OpenAI-compatible)."""

import os
import json
import requests
from typing import List, Optional, Iterator
from pydantic import BaseModel

from .models import SubConcept, ExtractedPICO


# NanoGPT API configuration
NANOGPT_BASE_URL = "https://nano-gpt.com/api/v1"
DEFAULT_MODEL = "Qwen/Qwen3-VL-235B-A22B-Instruct"


# =============================================================================
# Legacy Model (for backwards compatibility)
# =============================================================================

class ExtractedKeywords(BaseModel):
    """Structured output from keyword extraction (legacy)."""
    population: List[str] = []
    intervention: List[str] = []
    comparison: List[str] = []
    outcome: List[str] = []
    other: List[str] = []
    
    def all_keywords(self) -> List[str]:
        """Get all keywords as a flat list."""
        return (
            self.population + 
            self.intervention + 
            self.comparison + 
            self.outcome + 
            self.other
        )


# =============================================================================
# New Sub-Concept Extraction Prompt
# =============================================================================

SUBCONCEPT_EXTRACTION_PROMPT = """You are a medical literature search expert preparing a comprehensive systematic review search strategy.

Analyze the research question and extract search concepts organized by the PICO framework.
**IMPORTANT**: You must distinguish between the "Core Entity" (the disease/anatomy) and its "Modifiers" (state/severity/demographic).

## PICO Framework:
- **Population (P)**: Patient group, condition, disease.
- **Intervention (I)**: Treatment, drug, procedure.
- **Comparison (C)**: Control group, placebo (often implied).
- **Outcome (O)**: Clinical measurements or endpoints.

## Extraction Rules:
1. **Separation of Modifiers**: 
   - Extract the **noun phrase** as the `core_concept` (e.g., "Thyroid Eye Disease").
   - Extract adjectives limiting the scope as `modifier` (e.g., "active", "severe", "pediatric").
   - *Reason:* We expand the core concept using medical dictionaries but strict-match the modifier.

2. **Neutralize Outcomes (Avoid Bias)**:
   - Extract the clinical entity measured as `core_concept` (e.g., "Proptosis", "Pain").
   - Extract the change or movement as `direction_of_effect` (e.g., "reduction", "increase", "prevention").
   - *Reason:* We must search for the outcome itself, regardless of whether it increased or decreased.

3. **Atomic Entities**: 
   - Keep multi-word medical terms together in `core_concept` if they define a single entity (e.g., "Heart Attack", "Thyroid Eye Disease").
   - Do NOT split these into "Thyroid" and "Eye" and "Disease".

4. **No Abbreviations**: 
   - Expand all abbreviations in `core_concept` (e.g., use "Myocardial Infarction", not "MI").

5. **Separate Routes of Administration** (CRITICAL for drugs):
   - Drug CLASS goes in `core_concept` (e.g., "Steroids", "Antibiotics", "Glucocorticoids").
   - Route of administration goes in `modifier` (e.g., "intravenous", "oral", "topical", "intramuscular").
   - NEVER include route in core_concept (e.g., "intravenous steroids" → core: "Steroids", modifier: "intravenous").

## JSON Output Structure:
For each item in a PICO category, provide:
- "name": A short descriptive label
- "core_concept": The main medical entity (Noun phrase) - REQUIRED
- "modifier": Any adjective constraining the concept (Population/Intervention only, optional)
- "direction_of_effect": Any term indicating increase/decrease/change (Outcome only, optional)
- "explanation": Brief reasoning

## Example 1:
Question: "Is teprotumumab effective in reducing proptosis for active thyroid eye disease compared to intravenous steroids?"

```json
{{
  "population": [
    {{
      "name": "disease",
      "core_concept": "Thyroid Eye Disease",
      "modifier": "active",
      "explanation": "Core disease is TED; active is the specific disease state to filter by."
    }}
  ],
  "intervention": [
    {{
      "name": "drug",
      "core_concept": "teprotumumab",
      "modifier": null,
      "explanation": "Specific drug name."
    }}
  ],
  "comparison": [
    {{
      "name": "comparator_drug",
      "core_concept": "Steroids",
      "modifier": "intravenous",
      "explanation": "The drug CLASS is Steroids (core); intravenous is ROUTE OF ADMINISTRATION (modifier). Never include route in core_concept!"
    }}
  ],
  "outcome": [
    {{
      "name": "clinical_measurement",
      "core_concept": "proptosis",
      "direction_of_effect": "reduction",
      "explanation": "The clinical presentation is proptosis; reduction is the biased outcome direction (will be ignored)."
    }}
  ],
  "other": []
}}
```

## Example 2:
Question: "Management of pediatric patients with acute asthma exacerbation"

```json
{{
  "population": [
    {{
      "name": "condition",
      "core_concept": "Asthma",
      "modifier": "acute exacerbation",
      "explanation": "Core condition with severity modifier."
    }},
    {{
      "name": "demographic",
      "core_concept": "Pediatrics",
      "modifier": null,
      "explanation": "Age demographic group."
    }}
  ],
  "intervention": [],
  "comparison": [],
  "outcome": [],
  "other": []
}}
```

## Research Question:
{question}

## Output (JSON only, no explanation):
```json"""


# Legacy flat extraction prompt
EXTRACTION_PROMPT = """You are a medical literature search expert preparing a comprehensive systematic review search strategy.

Extract ALL relevant search keywords from the following research question and organize them into PICO categories.

## PICO Framework:
- **Population (P)**: Patient group, condition, disease, demographics, age groups
- **Intervention (I)**: Treatment, therapy, exposure, drug, procedure being studied
- **Comparison (C)**: Control group, placebo, alternative treatment, standard care
- **Outcome (O)**: Results measured, endpoints, effects, symptoms, mortality, quality of life

## Instructions:
1. Include the EXACT terms from the question
2. Include SYNONYMS and related terms (e.g., "heart attack" → "myocardial infarction", "MI")
3. Include BROADER and NARROWER terms where appropriate
4. Include common ABBREVIATIONS (e.g., "vitamin C" → "ascorbic acid", "vit C")
5. Be COMPREHENSIVE - more terms are better for systematic reviews
6. If a category doesn't apply, leave it as an empty array []

## Example:
Question: "What is the effect of aspirin on preventing heart attacks in diabetic patients?"

```json
{{
  "population": ["diabetic patients", "diabetes mellitus", "type 2 diabetes", "type 1 diabetes", "diabetics"],
  "intervention": ["aspirin", "acetylsalicylic acid", "ASA", "antiplatelet therapy"],
  "comparison": ["placebo", "no treatment", "standard care"],
  "outcome": ["heart attack", "myocardial infarction", "MI", "cardiovascular events", "cardiac events", "prevention", "mortality"],
  "other": []
}}
```

## Research Question:
{question}

## Output (JSON only, no explanation):
```json"""


class KeywordExtractor:
    """Extract search keywords from research questions using LLM."""
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        base_url: str = NANOGPT_BASE_URL
    ):
        """
        Initialize the keyword extractor.
        
        Args:
            api_key: NanoGPT API key (or set NANOGPT_API_KEY env var)
            model: Model to use for extraction
            base_url: API base URL
        """
        self.api_key = api_key or os.getenv("NANOGPT_API_KEY")
        self.model = model
        self.base_url = base_url
        
        if not self.api_key:
            print("Warning: No API key provided. Set NANOGPT_API_KEY env var.")
    
    def _get_headers(self) -> dict:
        """Get request headers."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
    
    def _call_llm(self, prompt: str, temperature: float = 0.1, top_p: float = 0.3) -> Optional[str]:
        """Call the LLM and return the response content."""
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._get_headers(),
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": temperature,
                    "top_p": top_p,
                    "stream": False
                },
                timeout=120  # Increased for complex extraction
            )
            
            if response.status_code != 200:
                print(f"API error: {response.status_code}")
                return None
            
            data = response.json()
            return data["choices"][0]["message"]["content"]
            
        except Exception as e:
            print(f"LLM call error: {e}")
            return None
    
    def extract_subconcepts(
        self, 
        question: str, 
        temperature: float = 0.1, 
        top_p: float = 0.3
    ) -> ExtractedPICO:
        """
        Extract sub-concepts from a research question.
        
        This is the NEW method that returns structured sub-concepts
        for proper AND/OR query building.
        
        Args:
            question: The research question to analyze
            temperature: LLM temperature (lower = more deterministic)
            top_p: LLM top_p (lower = more focused)
            
        Returns:
            ExtractedPICO with sub-concepts for each category
        """
        if not self.api_key:
            return self._manual_extract_subconcepts(question)
        
        prompt = SUBCONCEPT_EXTRACTION_PROMPT.format(question=question)
        content = self._call_llm(prompt, temperature, top_p)
        
        if content:
            return self._parse_subconcept_response(content)
        else:
            return self._manual_extract_subconcepts(question)
    
    def _parse_subconcept_response(self, content: str) -> ExtractedPICO:
        """Parse LLM response to extract sub-concepts."""
        content = content.strip()
        
        # Remove markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        
        content = content.strip()
        
        try:
            data = json.loads(content)
            
            # Parse each category
            pico = ExtractedPICO()
            
            for category in ["population", "intervention", "comparison", "outcome", "other"]:
                cat_data = data.get(category, [])
                sub_concepts = []
                
                for item in cat_data:
                    if isinstance(item, dict):
                        # NEW format with core_concept/modifier/direction_of_effect
                        core = item.get("core_concept", item.get("original_term", ""))
                        sub_concepts.append(SubConcept(
                            name=item.get("name", "unknown"),
                            core_concept=core,
                            modifier=item.get("modifier"),
                            direction_of_effect=item.get("direction_of_effect"),
                            explanation=item.get("explanation"),
                            # Legacy fields for backward compatibility
                            original_term=core,  # Map core_concept to original_term
                            expanded_terms=item.get("expanded_terms", [])
                        ))
                    elif isinstance(item, str):
                        # Legacy format - single term
                        sub_concepts.append(SubConcept(
                            name=item,
                            core_concept=item,
                            original_term=item,
                            expanded_terms=[]
                        ))
                
                setattr(pico, category, sub_concepts)
            
            return pico
            
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            import re
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                try:
                    return self._parse_subconcept_response(match.group())
                except Exception:
                    pass
        
        # Fallback
        return self._manual_extract_subconcepts("")
    
    def _manual_extract_subconcepts(self, question: str) -> ExtractedPICO:
        """Simple fallback extraction without LLM."""
        import re
        
        # Remove common stop words
        stop_words = {
            'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'must', 'shall',
            'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
            'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
            'through', 'during', 'before', 'after', 'above', 'below',
            'between', 'under', 'again', 'further', 'then', 'once',
            'here', 'there', 'when', 'where', 'why', 'how', 'all',
            'each', 'few', 'more', 'most', 'other', 'some', 'such',
            'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than',
            'too', 'very', 'just', 'and', 'but', 'if', 'or', 'because',
            'until', 'while', 'what', 'which', 'who', 'whom', 'this',
            'that', 'these', 'those', 'am', 'about', 'against', 'any',
            'both', 'effect', 'effects', 'effective', 'effectiveness'
        }
        
        # Extract words
        words = re.findall(r'\b[a-zA-Z]{3,}\b', question.lower())
        keywords = [w for w in words if w not in stop_words]
        
        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for w in keywords:
            if w not in seen:
                seen.add(w)
                unique.append(w)
        
        # Create sub-concepts from unique words
        sub_concepts = [
            SubConcept(name=w, original_term=w, expanded_terms=[])
            for w in unique
        ]
        
        return ExtractedPICO(other=sub_concepts)
    
    # =========================================================================
    # Legacy Methods (for backwards compatibility)
    # =========================================================================
    
    def extract(self, question: str, temperature: float = 0.1, top_p: float = 0.3) -> ExtractedKeywords:
        """
        Extract keywords from a research question (legacy method).
        
        Args:
            question: The research question to analyze
            temperature: LLM temperature (lower = more deterministic)
            top_p: LLM top_p (lower = more focused)
            
        Returns:
            ExtractedKeywords with PICO categories (flat lists)
        """
        if not self.api_key:
            return self._manual_extract(question)
        
        prompt = EXTRACTION_PROMPT.format(question=question)
        content = self._call_llm(prompt, temperature, top_p)
        
        if content:
            return self._parse_response(content)
        else:
            return self._manual_extract(question)
    
    def _parse_response(self, content: str) -> ExtractedKeywords:
        """Parse LLM response to extract JSON (legacy)."""
        content = content.strip()
        
        # Remove markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        
        content = content.strip()
        
        try:
            data = json.loads(content)
            return ExtractedKeywords(**data)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            import re
            match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                    return ExtractedKeywords(**data)
                except Exception:
                    pass
        
        # Fallback: treat as simple keywords
        return ExtractedKeywords(other=content.split())
    
    def _manual_extract(self, question: str) -> ExtractedKeywords:
        """Simple fallback keyword extraction without LLM (legacy)."""
        import re
        
        stop_words = {
            'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'must', 'shall',
            'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
            'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
            'through', 'during', 'before', 'after', 'above', 'below',
            'between', 'under', 'again', 'further', 'then', 'once',
            'here', 'there', 'when', 'where', 'why', 'how', 'all',
            'each', 'few', 'more', 'most', 'other', 'some', 'such',
            'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than',
            'too', 'very', 'just', 'and', 'but', 'if', 'or', 'because',
            'until', 'while', 'what', 'which', 'who', 'whom', 'this',
            'that', 'these', 'those', 'am', 'about', 'against', 'any',
            'both', 'effect', 'effects', 'effective', 'effectiveness'
        }
        
        words = re.findall(r'\b[a-zA-Z]{3,}\b', question.lower())
        keywords = [w for w in words if w not in stop_words]
        
        seen = set()
        unique = []
        for w in keywords:
            if w not in seen:
                seen.add(w)
                unique.append(w)
        
        return ExtractedKeywords(other=unique)
