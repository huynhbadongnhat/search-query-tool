import unittest

from src.models import ExtractedPICO, MeSHDescriptor, SearchSettings, SubConcept
from src.query_builder import QueryBuilder
from src.models import Database


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


if __name__ == "__main__":
    unittest.main()
