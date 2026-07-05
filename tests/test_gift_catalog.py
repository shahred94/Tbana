"""Country-aware TikTok gift catalogue behavior."""

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.api import gift_catalog


class GiftCatalogTest(unittest.TestCase):

    def setUp(self):
        gift_catalog._cached_catalogs.clear()

    def tearDown(self):
        gift_catalog._cached_catalogs.clear()

    def test_regions_are_extracted_and_sorted(self):
        page = """
        <a href="/gifts?region=SG">Singapore</a>
        <a href="/gifts?region=MY"><strong>Malaysia</strong></a>
        <a href="/gifts?region=SG">Singapore</a>
        """

        self.assertEqual(
            gift_catalog.parse_regions(page),
            [
                {
                    "code": "MY",
                    "name": "Malaysia",
                },
                {
                    "code": "SG",
                    "name": "Singapore",
                },
            ],
        )

    def test_catalog_cache_is_separate_for_each_country(self):
        regions = [
            {
                "code": "ID",
                "name": "Indonesia",
            },
            {
                "code": "MY",
                "name": "Malaysia",
            },
        ]

        def download(region):
            return (
                [
                    {
                        "name": f"{region} Gift",
                        "coins": 1,
                        "icon_url": "https://p16-webcast.tiktokcdn.com/gift.png",
                    }
                ],
                regions,
            )

        with (
            patch.object(
                gift_catalog,
                "_download_catalog",
                side_effect=download,
            ) as downloader,
            patch.object(
                gift_catalog.time,
                "monotonic",
                return_value=100,
            ),
        ):
            malaysia = gift_catalog.get_gift_catalog(
                "my"
            )
            malaysia_cached = gift_catalog.get_gift_catalog(
                "MY"
            )
            indonesia = gift_catalog.get_gift_catalog(
                "ID"
            )

        self.assertEqual(
            downloader.call_count,
            2,
        )
        self.assertFalse(malaysia["cached"])
        self.assertTrue(malaysia_cached["cached"])
        self.assertEqual(malaysia["region"], "MY")
        self.assertEqual(
            indonesia["gifts"][0]["name"],
            "ID Gift",
        )

    def test_invalid_region_is_rejected(self):
        with self.assertRaises(
            HTTPException
        ) as raised:
            gift_catalog.normalize_region(
                "MY&price=0"
            )

        self.assertEqual(
            raised.exception.status_code,
            400,
        )


if __name__ == "__main__":
    unittest.main()
