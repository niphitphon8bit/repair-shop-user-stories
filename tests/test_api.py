import concurrent.futures
import http.cookiejar
import json
import os
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
from app import server
from app.domain import *

PHOTO = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII="


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        server.DB = Path(cls.temp.name) / "test.sqlite"
        server.TEST_MODE = True
        os.environ["SHOP_INITIAL_PASSWORD"] = "test-password-123"
        server.init()
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.http.server_address[1]
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.temp.cleanup()

    def client(self):
        return urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )

    def request(self, path, data=None, client=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}" + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Content-Type": "application/json"},
        )
        try:
            response = (client or self.c).open(req)
            return response.status, json.load(response)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def login(self, id):
        c = self.client()
        self.assertEqual(
            self.request(
                "/api/login",
                dict(email=id + "@somdee.test", password="test-password-123"),
                c,
            )[0],
            200,
        )
        return c

    def setUp(self):
        self.c = self.login("owner")
        self.request("/api/test", dict(now="2026-11-11T12:00", reset=True))

    def intake(self, **extra):
        data = dict(
            name="ทดสอบ นามสกุล",
            phone="0812345678",
            device="D01",
            model="Acer",
            symptom="เปิดไม่ติด",
            accessories="ไม่มี",
            consent=True,
            passcode="secret-test-code",
            photos=[PHOTO, PHOTO],
            line="customer",
        )
        data.update(extra)
        return self.request("/api/jobs", data)

    def test_auth_and_security(self):
        self.assertEqual(self.request("/api/bootstrap", client=self.client())[0], 401)
        front = self.login("front")
        boy = self.login("boy")
        bank = self.login("bank")
        status, job = self.intake()
        self.assertEqual(status, 201)
        self.assertNotIn(
            "secret-test-code",
            json.dumps(self.request("/api/bootstrap", client=front)[1]),
        )
        self.assertEqual(
            self.request(
                "/api/jobs/" + job["id"],
                dict(action="quote", items=[dict(code="R03")], days=1),
                front,
            )[0],
            400,
        )
        self.assertEqual(
            self.request("/api/jobs/" + job["id"], dict(action="claim"), bank)[0], 400
        )
        self.assertEqual(
            self.request("/api/jobs/" + job["id"], dict(action="claim"), boy)[0], 200
        )
        self.assertIn(
            "secret-test-code",
            json.dumps(self.request("/api/bootstrap", client=boy)[1]),
        )
        self.request("/api/jobs/" + job["id"], dict(action="assign", assignee="em"))
        self.assertNotIn(
            "secret-test-code",
            json.dumps(self.request("/api/bootstrap", client=boy)[1]),
        )
        _, body = self.request(
            "/api/track", dict(id=job["id"], last4="0000"), self.client()
        )
        self.assertNotIn("ทดสอบ", json.dumps(body, ensure_ascii=False))

    def test_lockout_exact_boundary(self):
        c = self.client()
        for _ in range(5):
            self.assertEqual(
                self.request("/api/track", dict(id="SD-TEST-001", last4="0000"), c)[0],
                400,
            )
        self.assertEqual(
            self.request("/api/track", dict(id="SD-TEST-001", last4="2201"), c)[0], 429
        )
        self.request("/api/test", dict(now="2026-11-11T12:15"))
        self.assertEqual(
            self.request("/api/track", dict(id="SD-TEST-001", last4="2201"), c)[0], 200
        )

    def test_expiration_and_idempotent_response(self):
        data = dict(id="SD-TEST-001", last4="2201", accept=True)
        status, job = self.request("/api/track", data, self.client())
        self.assertEqual(status, 200)
        self.assertEqual(job["status"], STATUSES[3])
        first = job["quotes"][-1]["responded_at"]
        self.request("/api/test", dict(now="2026-11-11T13:00"))
        self.assertEqual(
            self.request("/api/track", data, self.client())[1]["quotes"][-1][
                "responded_at"
            ],
            first,
        )
        self.request("/api/test", dict(now="2026-11-11T12:00", reset=True))
        self.request("/api/test", dict(now="2026-11-12T00:00"))
        status, j = self.request(
            "/api/track", dict(id="SD-TEST-001", last4="2201"), self.client()
        )
        self.assertEqual(j["status"], STATUSES[6])

    def test_lifecycle_and_payment(self):
        _, j = self.intake()
        id = j["id"]
        self.request("/api/jobs/" + id, dict(action="claim", assignee="boy"))
        self.assertEqual(
            self.request("/api/jobs/" + id, dict(action="status", status=STATUSES[3]))[
                0
            ],
            400,
        )
        self.assertEqual(
            self.request(
                "/api/jobs/" + id,
                dict(action="quote", items=[dict(code="R03", parts=1290)], days=1),
            )[0],
            200,
        )
        status, j = self.request("/api/track", dict(id=id, last4="5678", accept=True))
        self.assertEqual(status, 200)
        self.assertEqual(j["bill"]["total"], 1290)
        self.assertEqual(
            self.request(
                "/api/jobs/" + id,
                dict(action="adjust", items=[dict(code="R03", parts=1449)]),
            )[0],
            200,
        )
        self.assertEqual(
            self.request(
                "/api/jobs/" + id,
                dict(action="adjust", items=[dict(code="R03", parts=1450)]),
            )[0],
            400,
        )
        self.request("/api/jobs/" + id, dict(action="status", status=STATUSES[5]))
        payment = dict(
            action="checkout",
            paid=1448,
            method="cash",
            receiver="ผู้รับแทน",
            last4="5678",
        )
        self.assertEqual(self.request("/api/jobs/" + id, payment)[0], 400)
        payment["paid"] = 1450
        status, j = self.request("/api/jobs/" + id, payment)
        self.assertEqual(status, 200)
        self.assertEqual(j["receipt"]["change"], 1)
        self.assertNotIn("passcode", j)
        self.assertEqual(self.request("/api/jobs/" + id, payment)[0], 400)

    def test_concurrent_receipt_numbers(self):
        def create(_):
            return self.intake()[1]["id"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            ids = list(pool.map(create, range(10)))
        self.assertEqual(len(set(ids)), 10)
        self.assertEqual(sorted(ids)[0], "SD-261111-001")
        self.assertEqual(sorted(ids)[-1], "SD-261111-010")

    def test_phone_clock(self):
        _, j = self.intake(line="")
        id = j["id"]
        self.request("/api/jobs/" + id, dict(action="claim", assignee="boy"))
        self.request(
            "/api/jobs/" + id, dict(action="quote", items=[dict(code="R03")], days=1)
        )
        self.request("/api/test", dict(now="2026-11-20T12:00"))
        _, j = self.request("/api/track", dict(id=id, last4="5678"))
        self.assertEqual(j["status"], STATUSES[2])
        self.request("/api/jobs/" + id, dict(action="called", index=1, success=True))
        self.assertEqual(
            self.request("/api/track", dict(id=id, last4="5678", accept=True))[0], 200
        )

    def test_intake_validation_and_test_tools(self):
        self.assertEqual(self.intake(photos=[PHOTO])[0], 400)
        self.assertEqual(self.intake(consent=False)[0], 400)
        self.assertEqual(self.intake(passcode="", no_passcode=False)[0], 400)
        jobs = self.request("/api/bootstrap")[1]["jobs"]
        byid = {x["id"]: x for x in jobs}
        self.assertEqual(len(jobs), 9)
        self.assertEqual(byid["SD-TEST-001"]["bill"]["total"], 1290)
        self.assertEqual(byid["SD-TEST-002"]["bill"]["total"], 3650)
        self.assertEqual(byid["SD-TEST-007"]["bill"]["total"], 100)
        self.assertTrue(byid["SD-TEST-004"]["warranties"][0]["eligible"])
        self.assertFalse(byid["SD-TEST-005"]["warranties"][0]["eligible"])

    def test_claim_workflow(self):
        intake = dict(
            symptom="แบตเสียซ้ำ", consent=True, no_passcode=True, photos=[PHOTO, PHOTO]
        )
        status, j = self.request(
            "/api/claim", dict(id="SD-TEST-004", item=0, intake=intake)
        )
        self.assertEqual(status, 201)
        id = j["id"]
        self.request("/api/jobs/" + id, dict(action="claim", assignee="boy"))
        status, j = self.request(
            "/api/jobs/" + id,
            dict(action="quote", items=[dict(code="R02", parts=900)], days=1),
        )
        self.assertEqual(status, 200)
        self.assertEqual(j["status"], STATUSES[3])
        self.assertEqual(j["bill"]["total"], 0)
        self.assertEqual(
            self.request("/api/claim", dict(id="SD-TEST-005", item=0, intake=intake))[
                0
            ],
            400,
        )

    def test_batch_checkout_atomic_and_void(self):
        payload = dict(
            ids=["SD-TEST-006", "SD-TEST-007"],
            receiver="เจ๊หงส์",
            last4="6605",
            method="cash",
            paid=99,
        )
        self.assertEqual(self.request("/api/checkout", payload)[0], 400)
        payload["paid"] = 101
        status, result = self.request("/api/checkout", payload)
        self.assertEqual(status, 200)
        self.assertEqual(result["receipt_id"], "RC-261111-001")
        jobs = {j["id"]: j for j in self.request("/api/bootstrap")[1]["jobs"]}
        for id in payload["ids"]:
            self.assertEqual(jobs[id]["status"], STATUSES[8])
            self.assertEqual(jobs[id]["receipt"]["combined_change"], 1)
        self.assertEqual(
            jobs["SD-TEST-006"]["receipt"]["id"], jobs["SD-TEST-007"]["receipt"]["id"]
        )
        self.request(
            "/api/jobs/SD-TEST-006", dict(action="void_receipt", reason="ทดสอบยกเลิก")
        )
        jobs = {j["id"]: j for j in self.request("/api/bootstrap")[1]["jobs"]}
        self.assertEqual(jobs["SD-TEST-007"]["receipt"]["void"], "ทดสอบยกเลิก")

    def test_notification_clock_requires_correct_quote(self):
        _, job = self.intake(line="")
        id = job["id"]
        self.request("/api/jobs/" + id, dict(action="claim", assignee="boy"))
        self.request(
            "/api/jobs/" + id, dict(action="quote", items=[dict(code="R03")], days=1)
        )
        self.request("/api/jobs/" + id, dict(action="called", index=0, success=True))
        _, j = self.request("/api/track", dict(id=id, last4="5678"))
        self.assertIsNone(j["quotes"][-1]["notified_at"])
        self.assertEqual(
            self.request("/api/track", dict(id=id, last4="5678", accept=True))[0], 400
        )
        self.request("/api/jobs/" + id, dict(action="called", index=1, success=True))
        self.assertEqual(
            self.request("/api/track", dict(id=id, last4="5678", accept=True))[0], 200
        )

    def test_photo_retention_and_account_lifecycle(self):
        _, j = self.intake()
        id = j["id"]
        with server.connect() as db:
            j = server.get_job(db, id)
            j["status"] = STATUSES[8]
            j["returned_at"] = "2025-11-11T12:00:00+07:00"
            server.save(db, j)
        jobs = {j["id"]: j for j in self.request("/api/bootstrap")[1]["jobs"]}
        self.assertEqual(len(jobs[id]["photos"]), 2)
        self.request("/api/test", dict(now="2026-11-12T12:00"))
        jobs = {j["id"]: j for j in self.request("/api/bootstrap")[1]["jobs"]}
        self.assertEqual(jobs[id]["photos"], [])
        self.assertEqual(
            self.request("/api/users", dict(id="boy", active=False))[0], 400
        )
        self.assertEqual(
            self.request(
                "/api/users",
                dict(
                    id="front2",
                    name="หน้าร้านใหม่",
                    role="front",
                    active=True,
                    password="new-password-123",
                ),
            )[0],
            200,
        )
        self.assertEqual(
            self.request("/api/users", dict(id="front2", active=False))[0], 200
        )


if __name__ == "__main__":
    unittest.main()
