import unittest
from datetime import datetime, timedelta
from app.domain import *


class ShopRules(unittest.TestCase):
    def setUp(self):
        self.at = datetime(2026, 11, 11, 12, tzinfo=TZ)

    def test_working_days(self):
        friday = datetime(2026, 11, 6, 12, tzinfo=TZ)
        self.assertEqual(pickup(friday, 1, "D01"), "2026-11-07")
        saturday = friday + timedelta(days=1)
        self.assertEqual(pickup(saturday, 1, "D01"), "2026-11-09")
        self.assertEqual(pickup(saturday, 2, "D01"), "2026-11-10")
        self.assertEqual(pickup(saturday, 1, "D04"), "2026-11-10")
        self.assertEqual(
            pickup(datetime(2026, 11, 10, 12, tzinfo=TZ), 1, "D01", ["2026-11-11"]),
            "2026-11-12",
        )
        with self.assertRaises(ValueError):
            pickup(friday, 0, "D01")

    def test_rush_rounding_and_deadline(self):
        for labor, expected in [
            (300, 150),
            (350, 180),
            (450, 230),
            (700, 350),
            (710, 360),
        ]:
            self.assertEqual(rush_fee(labor), expected)
        for minute, expected in [
            (0, "2026-11-07T19:00:00+07:00"),
            (1, "2026-11-09T10:00:00+07:00"),
        ]:
            self.assertEqual(
                rush_deadline(datetime(2026, 11, 6, 19, minute, tzinfo=TZ)), expected
            )

    def test_storage_boundaries(self):
        for days, expected in [(59, 0), (60, 0), (61, 20), (65, 100)]:
            self.assertEqual(
                storage((self.at - timedelta(days=days)).isoformat(), self.at), expected
            )

    def test_quote_rules(self):
        self.assertEqual(
            quote_items([dict(code="R03", parts=1290)], "D01")[0]["labor"], 300
        )
        for data, device in [
            ([dict(code="R09", labor=1499)], "D01"),
            ([dict(code="R03", parts=1.25)], "D01"),
            ([dict(code="R01")], "D04"),
        ]:
            with self.assertRaises(ValueError):
                quote_items(data, device)

    def test_billing(self):
        job = dict(
            status=STATUSES[5],
            device="D01",
            quotes=[dict(items=[dict(labor=300, parts=1290)])],
        )
        self.assertEqual(payable(job, self.at)["total"], 1290)
        job["discount"] = 100
        self.assertEqual(payable(job, self.at)["total"], 1190)
        job.update(
            discount=0, rush=True, quotes=[dict(items=[dict(labor=500, parts=3200)])]
        )
        self.assertEqual(payable(job, self.at)["total"], 3650)
        job["rush_late"] = True
        self.assertEqual(payable(job, self.at)["total"], 3400)
        job = dict(
            status=STATUSES[5],
            device="D01",
            quotes=[dict(items=[dict(labor=299, parts=0)])],
            notified_at=(self.at - timedelta(days=65)).isoformat(),
        )
        self.assertEqual(payable(job, self.at)["total"], 100)
        job.update(
            closing_reason="cancelled",
            manual_charges=dict(inspection=300, labor=150, parts=1290),
        )
        self.assertEqual(payable(job, self.at)["total"], 1840)

    def test_integer_money(self):
        for value in [-1, 100.25, True, "100"]:
            with self.assertRaises(ValueError):
                money(value)
        self.assertEqual(money(0), 0)


if __name__ == "__main__":
    unittest.main()
