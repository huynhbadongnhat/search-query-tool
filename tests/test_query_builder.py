import unittest

from src.models import ExtractedPICO, MeSHDescriptor, SearchSettings, SubConcept
from src.query_builder import QueryBuilder
from src.models import Database
from src.term_utils import rank_terms_by_relevance


class QueryBuilderTests(unittest.TestCase):
    def test_pubmed_escapes_quotes_and_keeps_modifier_separate(self):
        pico = ExtractedPICO(
            intervention=[
                SubConcept(
                    name="drug",
                    core_concept='alpha "blocker"',
                    original_term='alpha "blocker"',
                    modifier="oral",
                )
            ]
        )

        query = QueryBuilder(SearchSettings(proximity_distance=2)).build_pico_query(
            pico,
            Database.PUBMED,
        )

        self.assertIn('"alpha blocker"[Title/Abstract:~2]', query.query_string)
        self.assertIn("oral[tiab]", query.query_string)
        self.assertIn(" AND ", query.query_string)

    def test_api_mesh_backbone_terms_remain_controlled_vocabulary(self):
        pico = ExtractedPICO(
            population=[
                SubConcept(
                    name="condition",
                    core_concept="Thyroid Eye Disease",
                    original_term="Thyroid Eye Disease",
                    mesh_descriptor=MeSHDescriptor(
                        ui="API:UMLS",
                        name="Graves Ophthalmopathy",
                        entry_terms=["Exophthalmos"],
                    ),
                )
            ]
        )

        query = QueryBuilder(SearchSettings()).build_pico_query(pico, Database.PUBMED)

        self.assertIn('"Graves Ophthalmopathy"[MeSH Terms:noexp]', query.query_string)
        self.assertIn("Exophthalmos[MeSH Terms:noexp]", query.query_string)

    def test_text_field_setting_can_disable_tiab_tags(self):
        pico = ExtractedPICO(
            outcome=[
                SubConcept(
                    name="outcome",
                    core_concept="migraine frequency",
                    original_term="migraine frequency",
                )
            ]
        )

        settings = SearchSettings(include_title_abstract=False)
        query = QueryBuilder(settings).build_pico_query(pico, Database.PUBMED)

        self.assertEqual('"migraine frequency"', query.query_string)

    def test_english_filter_removes_non_english_expanded_terms(self):
        pico = ExtractedPICO(
            population=[
                SubConcept(
                    name="condition",
                    core_concept="diabetes mellitus",
                    original_term="diabetes mellitus",
                    umls_synonyms=["糖尿病", "diabetes"],
                )
            ]
        )

        query = QueryBuilder(SearchSettings()).build_pico_query(pico, Database.PUBMED)

        self.assertIn("diabetes[tiab]", query.query_string)
        self.assertNotIn("糖尿病", query.query_string)

    def test_english_filter_can_be_disabled(self):
        pico = ExtractedPICO(
            population=[
                SubConcept(
                    name="condition",
                    core_concept="diabetes mellitus",
                    original_term="diabetes mellitus",
                    umls_synonyms=["糖尿病"],
                )
            ]
        )

        settings = SearchSettings(english_only_terms=False)
        query = QueryBuilder(settings).build_pico_query(pico, Database.PUBMED)

        self.assertIn("糖尿病[tiab]", query.query_string)

    def test_expanded_terms_are_ranked_by_deterministic_relevance(self):
        ranked = rank_terms_by_relevance(
            ["unrelated therapy", "diabetes", "diabetes mellitus"],
            ["diabetes mellitus"],
            english_only=True,
        )

        self.assertEqual("diabetes mellitus", ranked[0])


if __name__ == "__main__":
    unittest.main()
