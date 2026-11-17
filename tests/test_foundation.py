import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from globalosint.database import initialize, connect
from globalosint.models import SourceInput, SourceKind, SourceStatus
from globalosint.registry import add_source, assess_source, list_sources


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        initialize(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_source_is_created_as_candidate_and_persists(self):
        with closing(connect(self.path)) as db, db:
            source = add_source(db, SourceInput("OMS", "https://www.who.int/", SourceKind.INSTITUTIONAL,
                                               ("en", "pt"), ("health",)))
        with closing(connect(self.path)) as db, db:
            loaded = list_sources(db)[0]
        self.assertEqual(source.id, loaded.id)
        self.assertEqual(SourceStatus.CANDIDATE, loaded.status)
        self.assertEqual(("en", "pt"), loaded.languages)

    def test_invalid_language_is_rejected(self):
        with closing(connect(self.path)) as db, db:
            with self.assertRaises(ValueError):
                add_source(db, SourceInput("Fonte", "https://example.org", SourceKind.OTHER,
                                           ("xx",), ("health",)))

    def test_assessment_is_bounded_and_filterable(self):
        with closing(connect(self.path)) as db, db:
            source = add_source(db, SourceInput("OMS", "https://www.who.int/", SourceKind.INSTITUTIONAL,
                                               ("en",), ("health",)))
            with self.assertRaises(ValueError):
                assess_source(db, source.id, SourceStatus.APPROVED, 101)
            assessed = assess_source(db, source.id, SourceStatus.APPROVED, 85, "Avaliação inicial")
            self.assertEqual(85, assessed.reliability_score)
            self.assertEqual(1, len(list_sources(db, SourceStatus.APPROVED)))

    def test_duplicate_url_is_rejected(self):
        with closing(connect(self.path)) as db, db:
            payload = SourceInput("OMS", "https://www.who.int/", SourceKind.INSTITUTIONAL,
                                  ("en",), ("health",))
            add_source(db, payload)
            with self.assertRaises(sqlite3.IntegrityError):
                add_source(db, payload)


if __name__ == "__main__":
    unittest.main()
