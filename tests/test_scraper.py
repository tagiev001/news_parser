import unittest

from bs4 import BeautifulSoup

from src import crawler_service as scraper


class ScraperTests(unittest.TestCase):
    def test_parses_numeric_and_russian_publication_dates(self):
        self.assertEqual(scraper.parse_published_date("Published 5/10/2026"), "05.10.26")
        self.assertEqual(scraper.parse_published_date("5 октября 2026"), "05.10.26")
        self.assertIsNone(scraper.parse_published_date("date unavailable"))

    def test_extracts_article_text_without_script_content(self):
        article = BeautifulSoup(
            "<article><p>First paragraph.</p><script>ignore()</script>"
            "<p>Second paragraph!</p></article>",
            "html.parser",
        )

        self.assertEqual(
            scraper.extract_article_text(article),
            "First paragraph.\nSecond paragraph!",
        )


if __name__ == "__main__":
    unittest.main()
