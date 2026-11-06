"""Local repair-shop application; Python 3.12+, no third-party runtime dependencies."""

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from urllib.parse import urlparse
from .domain import *

ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.environ.get("SHOP_DB", str(ROOT / ".data/shop.sqlite3")))
LOCK = threading.RLock()
TEST_MODE = os.environ.get("SHOP_TEST_MODE") == "1"


def encode(value):
    return json.dumps(value, ensure_ascii=False)


def password_hash(password, salt=None):
    require(
        isinstance(password, str) and 10 <= len(password) <= 200,
        "รหัสผ่านต้องยาว 10–200 ตัวอักษร",
    )
    salt = salt or secrets.token_hex(16)
    return (
        salt
        + ":"
        + hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    )


def verify(password, stored):
    try:
        return hmac.compare_digest(
            password_hash(password, stored.split(":")[0]), stored
        )
    except (ValueError, AttributeError):
        return False


def connect():
    db = sqlite3.connect(DB, timeout=20)
    db.row_factory = sqlite3.Row
    return db


def setting(db, key, default=None):
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_setting(db, key, value):
    db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, encode(value)))


def now(db):
    fixed = setting(db, "test_now") if TEST_MODE else None
    return (
        datetime.fromisoformat(fixed).replace(tzinfo=TZ) if fixed else datetime.now(TZ)
    )


def get_job(db, id):
    row = db.execute("SELECT data FROM jobs WHERE id=?", (id,)).fetchone()
    require(row is not None, "ไม่พบงานซ่อม")
    return json.loads(row[0])


def save(db, job):
    db.execute("INSERT OR REPLACE INTO jobs VALUES (?,?)", (job["id"], encode(job)))


def sequence(db, prefix, at):
    key = prefix + "-" + at.strftime("%y%m%d")
    db.execute(
        "INSERT INTO counters VALUES (?,1) ON CONFLICT(key) DO UPDATE SET value=value+1",
        (key,),
    )
    return f'{key}-{db.execute("SELECT value FROM counters WHERE key=?",(key,)).fetchone()[0]:03d}'


def audit(job, at, actor, text, public=False):
    job["timeline"].append(
        dict(at=at.isoformat(), actor=actor, text=text, public=public)
    )


def notice(job, at, text):
    job["notifications"].append(
        dict(
            at=at.isoformat(),
            channel="LINE จำลอง" if job.get("line") else "โทรศัพท์",
            text=text,
            called=False,
            status=job["status"],
            quote_version=(
                job["quotes"][-1]["version"]
                if job["status"] == STATUSES[2] and job["quotes"]
                else None
            ),
        )
    )
    if (
        job.get("line")
        and job["status"] in STATUSES[5:8]
        and not job.get("notified_at")
    ):
        job["notified_at"] = at.isoformat()


def change(job, status, at, actor):
    job["status"] = status
    audit(job, at, actor, status, True)
    notice(
        job,
        at,
        f"{job['id']} • {status}"
        + (f" • นัดรับ {job['pickup']}" if job.get("pickup") else ""),
    )


def public_job(job, at):
    names = job["name"].split()
    result = {
        k: job.get(k)
        for k in (
            "id",
            "device",
            "model",
            "symptom",
            "status",
            "pickup",
            "rush",
            "deadline",
            "quotes",
            "closing_reason",
        )
    }
    result["name"] = names[0] + (" " + names[1][0] + "." if len(names) > 1 else "")
    result["timeline"] = [
        {k: x[k] for k in ("at", "text")} for x in job["timeline"] if x.get("public")
    ]
    result["bill"] = payable(job, at)
    return result


def staff_job(job, user, at):
    result = dict(job)
    if user["role"] != "owner" and job.get("assignee") != user["id"]:
        result.pop("passcode", None)
    result["bill"] = payable(job, at)
    result["needs_charges"] = (
        job.get("closing_reason")
        in ("rejected_revision", "expired_revision", "cancelled", "failed")
        and job.get("manual_charges") is None
    )
    due = job.get("deadline") if job.get("rush") else job.get("pickup")
    result["urgency"] = "normal"
    if due and job["status"] in STATUSES[:5]:
        if job.get("rush"):
            result["urgency"] = "late" if at > datetime.fromisoformat(due) else "soon"
        else:
            delta = (date.fromisoformat(due) - at.date()).days
            result["urgency"] = (
                "late" if delta < 0 else "soon" if delta <= 1 else "normal"
            )
    result["over60"] = bool(
        job.get("notified_at")
        and job["status"] in STATUSES[5:8]
        and (at.date() - datetime.fromisoformat(job["notified_at"]).date()).days > 60
    )
    returned = job.get("returned_at")
    result["warranties"] = []
    if returned:
        elapsed = (
            at.date()
            - datetime.fromisoformat(job.get("warranty_origin_at") or returned).date()
        ).days
        for item in job.get(
            "current_items", job["quotes"][-1]["items"] if job["quotes"] else []
        ):
            result["warranties"].append(
                dict(
                    name=item["name"],
                    days=item["warranty"],
                    eligible=(
                        not job.get("closing_reason") or job.get("warranty_override")
                    )
                    and item["warranty"] > 0
                    and elapsed <= item["warranty"],
                    remaining=max(0, item["warranty"] - elapsed),
                )
            )
    return result


def maintain(db):
    at = now(db)
    for row in db.execute("SELECT data FROM jobs").fetchall():
        job = json.loads(row[0])
        changed = False
        if job["status"] == STATUSES[2] and job["quotes"]:
            q = job["quotes"][-1]
            sent = q.get("notified_at")
            if sent and (at.date() - datetime.fromisoformat(sent).date()).days > 7:
                job["closing_reason"] = (
                    "expired_first" if len(job["quotes"]) == 1 else "expired_revision"
                )
                change(job, STATUSES[6], at, "ระบบ")
                changed = True
        if job.get("returned_at"):
            returned = datetime.fromisoformat(job["returned_at"]).date()
            try:
                anniversary = returned.replace(year=returned.year + 1)
            except ValueError:
                anniversary = returned.replace(year=returned.year + 1, day=28)
            if at.date() > anniversary and job.get("photos"):
                job["photos"] = []
                changed = True
        if (
            job.get("pickup")
            and job["status"] in STATUSES[1:5]
            and at.hour >= 10
            and at.date().isoformat() >= job["pickup"]
        ):
            marker = at.date().isoformat()
            if job.get("reminder_date") != marker:
                notice(
                    job,
                    at,
                    "งานซ่อมยังไม่เสร็จตามนัด ร้านกำลังติดตามและจะแจ้งความคืบหน้า",
                )
                audit(job, at, "ระบบ", "เตือนงานซ่อมถึงวันนัด/เลยนัด")
                job["reminder_date"] = marker
                changed = True
        if changed:
            save(db, job)


def init():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT,role TEXT,hash TEXT,active INTEGER);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT,expires TEXT);
        CREATE TABLE IF NOT EXISTS counters(key TEXT PRIMARY KEY,value INTEGER);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY,count INTEGER,until TEXT);
        """)
        if not db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            initial = os.environ.get("SHOP_INITIAL_PASSWORD") or secrets.token_urlsafe(
                15
            )
            for id, name, role in [
                ("owner", "คุณเก่ง", "owner"),
                ("front", "น้องมิ้นท์", "front"),
                ("boy", "ช่างบอย", "tech"),
                ("bank", "ช่างแบงค์", "tech"),
                ("em", "ช่างเอ็ม", "tech"),
            ]:
                db.execute(
                    "INSERT INTO users VALUES (?,?,?,?,1)",
                    (id, name, role, password_hash(initial)),
                )
            print("บัญชีเริ่มต้น: owner/front/boy/bank/em @somdee.test", flush=True)
            print(
                "รหัสผ่านเริ่มต้น (เปลี่ยนได้ในหน้าจัดการบัญชี): " + initial, flush=True
            )
        if setting(db, "catalog") is None:
            set_setting(db, "catalog", CATALOG)
        if setting(db, "inspection") is None:
            set_setting(db, "inspection", dict(D01=300, D02=300, D03=200, D04=300))
    os.chmod(DB, 0o600)


def new_job(db, data, actor):
    at = now(db)
    for key in ("name", "phone", "device", "model", "symptom", "accessories"):
        require(
            isinstance(data.get(key), str)
            and bool(data[key].strip())
            and len(data[key]) <= 1000,
            "กรุณากรอก " + key,
        )
    require(
        re.fullmatch(r"0\d{8,9}", data["phone"]) is not None,
        "เบอร์โทรต้องเป็นตัวเลข 9–10 หลักขึ้นต้นด้วย 0",
    )
    require(data["device"] in DEVICES, "ประเภทเครื่องไม่ถูกต้อง")
    require(data.get("consent") is True, "ต้องยอมรับความเสี่ยงเรื่องข้อมูล")
    require(
        data.get("passcode") or data.get("no_passcode") is True,
        "ต้องระบุรหัสเครื่องหรือรับทราบว่าไม่ให้รหัส",
    )
    photos = data.get("photos", [])
    require(
        isinstance(photos, list) and 2 <= len(photos) <= 6,
        "ต้องมีรูปสภาพเครื่อง 2–6 รูป",
    )
    for photo in photos:
        require(
            isinstance(photo, str)
            and len(photo) <= 2_800_000
            and photo.startswith(
                (
                    "data:image/png;base64,",
                    "data:image/jpeg;base64,",
                    "data:image/webp;base64,",
                )
            ),
            "รูปต้องเป็น JPEG PNG หรือ WebP ขนาดไม่เกิน 2 MB",
        )
        try:
            image = base64.b64decode(photo.split(",", 1)[1], validate=True)
        except Exception:
            raise ValueError("ไฟล์รูปไม่ถูกต้อง")
        require(
            image.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff"))
            or image[:4] == b"RIFF"
            and image[8:12] == b"WEBP",
            "ข้อมูลรูปไม่ถูกต้อง",
        )
    job = {
        k: data.get(k, "")
        for k in (
            "name",
            "phone",
            "device",
            "model",
            "symptom",
            "accessories",
            "line",
            "serial",
            "notes",
            "passcode",
        )
    }
    require(
        all(isinstance(x, str) and len(x) <= 2000 for x in job.values()),
        "ข้อความยาวเกินกำหนด",
    )
    job.update(
        id=sequence(db, "SD", at),
        created_at=at.isoformat(),
        status=STATUSES[0],
        assignee=None,
        photos=photos,
        consent=True,
        no_passcode=bool(data.get("no_passcode")),
        rush_requested=bool(data.get("rush_requested")),
        quotes=[],
        timeline=[],
        notifications=[],
        inspection_fee=setting(db, "inspection")[data["device"]],
    )
    audit(job, at, actor, STATUSES[0], True)
    save(db, job)
    return job


def allowed(user, *roles):
    require(user["role"] in roles, "ไม่มีสิทธิ์ทำรายการนี้")


def technician(user, job):
    require(
        user["role"] == "owner"
        or user["role"] == "tech"
        and job.get("assignee") == user["id"],
        "เฉพาะเจ้าของร้านหรือช่างผู้รับงาน",
    )


def respond(db, job, accept, rush, actor):
    require(job["quotes"], "ยังไม่มีใบเสนอราคา")
    q = job["quotes"][-1]
    if q.get("decision"):
        require(
            q["decision"] == ("accepted" if accept else "rejected"),
            "ใบเสนอราคานี้ตอบแล้ว",
        )
        return
    require(job["status"] == STATUSES[2], "งานซ่อมไม่อยู่ระหว่างรอยืนยัน")
    require(q.get("notified_at"), "กรุณาให้ร้านโทรแจ้งใบเสนอราคาก่อน")
    at = now(db)
    require(
        (at.date() - datetime.fromisoformat(q["notified_at"]).date()).days <= 7,
        "ใบเสนอราคาหมดอายุแล้ว",
    )
    require(not rush or q["rush_eligible"], "ใบเสนอราคานี้ไม่รองรับงานด่วน")
    q["decision"] = "accepted" if accept else "rejected"
    q["responded_at"] = at.isoformat()
    if accept:
        job["rush"] = bool(rush)
        job["accepted_base"] = q["total"]
        job["current_items"] = q["items"]
        job.pop("closing_reason", None)
        job["pickup"] = pickup(
            at, q["days"], job["device"], setting(db, "holidays", [])
        )
        job["deadline"] = (
            rush_deadline(at, setting(db, "holidays", [])) if rush else None
        )
        job["rush_late"] = False
        change(job, STATUSES[3], at, actor)
    else:
        job["closing_reason"] = (
            "rejected_first" if len(job["quotes"]) == 1 else "rejected_revision"
        )
        change(job, STATUSES[6], at, actor)


def action(db, job, data, user, receipt_id=None):
    at = now(db)
    kind = data.get("action")
    actor = user["name"]
    status = job["status"]
    if kind == "claim":
        allowed(user, "owner", "tech")
        require(status == STATUSES[0] and not job.get("assignee"), "มีช่างรับงานแล้ว")
        assignee = (
            data.get("assignee", user["id"]) if user["role"] == "owner" else user["id"]
        )
        require(
            assignee in SKILLS
            and db.execute(
                "SELECT 1 FROM users WHERE id=? AND active=1", (assignee,)
            ).fetchone(),
            "กรุณาเลือกช่างที่เปิดใช้งาน",
        )
        require(
            user["role"] == "owner" or job["device"] in SKILLS[assignee],
            "ช่างไม่รับประเภทเครื่องนี้",
        )
        job["assignee"] = assignee
        change(job, STATUSES[1], at, actor)
    elif kind == "assign":
        allowed(user, "owner")
        require(status != STATUSES[8], "งานซ่อมปิดแล้ว")
        require(
            data.get("assignee") in SKILLS
            and db.execute(
                "SELECT 1 FROM users WHERE id=? AND active=1", (data["assignee"],)
            ).fetchone(),
            "ช่างไม่ถูกต้อง",
        )
        job["assignee"] = data["assignee"]
        audit(job, at, actor, "มอบงานให้ " + job["assignee"])
    elif kind == "quote":
        technician(user, job)
        require(status in STATUSES[1:5], "สถานะนี้ออกใบเสนอราคาไม่ได้")
        items = quote_items(data.get("items"), job["device"], setting(db, "catalog"))
        if job.get("claim_of"):
            original = get_job(db, job["claim_of"])
            original_items = original.get(
                "current_items", original["quotes"][-1]["items"]
            )
            covered = original_items[job["claim_item"]]
            for item in items:
                if item["code"] == covered["code"] and item["name"] == covered["name"]:
                    item["labor"] = 0
                    item["parts"] = 0
        days = data.get("days")
        pickup(at, days, job["device"], setting(db, "holidays", []))
        eligible = (
            not data.get("order_parts")
            and not data.get("cannot_24h")
            and not any(x["code"] == "R09" for x in items)
        )
        q = dict(
            version=len(job["quotes"]) + 1,
            items=items,
            days=days,
            total=sum(x["labor"] + x["parts"] for x in items),
            sent_at=at.isoformat(),
            notified_at=at.isoformat() if job.get("line") else None,
            rush_eligible=eligible,
            data_loss=bool(data.get("data_loss")),
            rush_reason=(
                "" if eligible else "ต้องสั่งอะไหล่ / กู้ข้อมูล / ทำไม่ทัน 24 ชั่วโมง"
            ),
        )
        job["quotes"].append(q)
        change(job, STATUSES[2], at, actor)
        if job.get("claim_of") and q["total"] == 0:
            q["notified_at"] = at.isoformat()
            respond(db, job, True, False, "ระบบ (เคลม ฿0)")
    elif kind == "adjust":
        technician(user, job)
        require(status == STATUSES[3], "ปรับราคาได้ระหว่างกำลังซ่อม")
        items = quote_items(data.get("items"), job["device"], setting(db, "catalog"))
        total = sum(x["labor"] + x["parts"] for x in items)
        require(
            total * 100 <= job["accepted_base"] * 110,
            "ยอดเพิ่มเกิน 10% ต้องส่งใบเสนอราคาฉบับใหม่",
        )
        job["current_items"] = items
        audit(job, at, actor, "ปรับราคาค่าบริการเป็น " + str(total))
        notice(job, at, "ปรับราคาค่าบริการเป็น ฿" + str(total))
    elif kind == "respond":
        allowed(user, "owner", "front")
        require(type(data.get("accept")) is bool, "กรุณาระบุคำตอบ")
        respond(
            db, job, data["accept"], bool(data.get("rush")), actor + " (ทางโทรศัพท์)"
        )
    elif kind == "status":
        technician(user, job)
        target = data.get("status")
        transitions = {
            STATUSES[1]: [STATUSES[7]],
            STATUSES[3]: [STATUSES[4], STATUSES[5], STATUSES[7]],
            STATUSES[4]: [STATUSES[3], STATUSES[7]],
            STATUSES[5]: [STATUSES[3]],
        }
        require(target in transitions.get(status, []), "เปลี่ยนสถานะนี้ไม่ได้")
        if target == STATUSES[4]:
            day = date.fromisoformat(data.get("pickup", ""))
            require(
                day >= at.date()
                and working_day(day, job["device"], setting(db, "holidays", [])),
                "วันนัดใหม่ต้องเป็นวันทำการที่ยังไม่ผ่าน",
            )
            job["pickup"] = day.isoformat()
            job["rush"] = False
        if target == STATUSES[7]:
            job["closing_reason"] = (
                "unrepairable" if status == STATUSES[1] else "failed"
            )
        if target == STATUSES[5]:
            job["finished_at"] = at.isoformat()
            job["rush_late"] = bool(
                job.get("rush") and at > datetime.fromisoformat(job["deadline"])
            )
        if status == STATUSES[5]:
            job.pop("notified_at", None)
        change(job, target, at, actor)
    elif kind == "cancel":
        allowed(user, "owner")
        require(
            status in (STATUSES[3], STATUSES[4]),
            "ยกเลิกได้เฉพาะระหว่างซ่อมหรือรออะไหล่",
        )
        require(bool(data.get("reason")), "ต้องระบุเหตุผล")
        job["closing_reason"] = "cancelled"
        job.pop("manual_charges", None)
        audit(job, at, actor, str(data["reason"]))
        change(job, STATUSES[6], at, actor)
    elif kind == "reopen":
        allowed(user, "owner", "front")
        require(status == STATUSES[6], "เปิดงานกลับไม่ได้")
        q = job["quotes"][-1]
        job["current_items"] = q["items"]
        job["accepted_base"] = q["total"]
        job["rush"] = False
        job["pickup"] = pickup(
            at, q["days"], job["device"], setting(db, "holidays", [])
        )
        for key in ("closing_reason", "notified_at", "manual_charges"):
            job.pop(key, None)
        change(job, STATUSES[3], at, actor)
    elif kind == "contact":
        allowed(user, "owner", "front")
        require(status != STATUSES[8], "งานซ่อมปิดแล้ว")
        require(
            bool(str(data.get("name", "")).strip())
            and re.fullmatch(r"0\d{8,9}", str(data.get("phone", ""))),
            "ชื่อหรือเบอร์ไม่ถูกต้อง",
        )
        audit(
            job,
            at,
            actor,
            "แก้ข้อมูลติดต่อ จาก "
            + encode({k: job[k] for k in ("name", "phone", "line")}),
        )
        for k in ("name", "phone", "line"):
            job[k] = str(data.get(k, ""))[:1000]
    elif kind == "called":
        allowed(user, "owner", "front")
        index = data.get("index")
        require(
            type(index) is int and 0 <= index < len(job["notifications"]),
            "ไม่พบข้อความ",
        )
        n = job["notifications"][index]
        if not n["called"]:
            n["called"] = bool(data.get("success"))
            n["attempted_at"] = at.isoformat()
            if n["called"]:
                n["called_at"] = at.isoformat()
                if (
                    status in STATUSES[5:8]
                    and n.get("status") == status
                    and not job.get("notified_at")
                ):
                    job["notified_at"] = at.isoformat()
                if (
                    status == STATUSES[2]
                    and job["quotes"]
                    and n.get("quote_version") == job["quotes"][-1]["version"]
                    and not job["quotes"][-1].get("notified_at")
                ):
                    job["quotes"][-1]["notified_at"] = at.isoformat()
            audit(job, at, actor, "โทรแจ้งแล้ว" if n["called"] else "โทรไม่ติด")
    elif kind == "charges":
        allowed(user, "owner")
        require(status in STATUSES[5:8], "กำหนดยอดเมื่อรอคืนเครื่องเท่านั้น")
        reason = str(data.get("reason", "")).strip()
        require(bool(reason), "ต้องระบุเหตุผล")
        if data.get("manual_charges") is not None:
            require(
                job.get("closing_reason")
                in ("cancelled", "rejected_revision", "expired_revision", "failed"),
                "กรณีนี้ไม่ต้องกรอกยอดปิดงาน",
            )
            charges = {
                k: money(data["manual_charges"].get(k, 0))
                for k in ("inspection", "labor", "parts")
            }
            require(
                job.get("closing_reason") != "failed"
                or charges["inspection"] == charges["labor"] == 0,
                "ซ่อมไม่สำเร็จเก็บได้เฉพาะอะไหล่ที่ลูกค้าเก็บไว้",
            )
            job["manual_charges"] = charges
        job["discount"] = money(data.get("discount", 0))
        if data.get("waive"):
            job["inspection_fee"] = 0
        job["warranty_override"] = bool(data.get("warranty_override"))
        job["restore_rush"] = bool(data.get("restore_rush"))
        audit(job, at, actor, "ปรับยอด/ส่วนลด: " + reason)
    elif kind == "checkout":
        allowed(user, "owner", "front")
        require(status in STATUSES[5:8], "ยังคืนเครื่องไม่ได้")
        require(
            job.get("closing_reason")
            not in ("cancelled", "rejected_revision", "expired_revision", "failed")
            or job.get("manual_charges") is not None,
            "รอเจ้าของร้านกำหนดยอดปิดงาน",
        )
        require(
            str(data.get("last4", "")) == job["phone"][-4:], "เบอร์ 4 ตัวท้ายไม่ถูกต้อง"
        )
        require(
            bool(str(data.get("receiver", "")).strip()), "ต้องระบุชื่อผู้รับเครื่อง"
        )
        require(data.get("method") in ("cash", "transfer"), "กรุณาเลือกเงินสดหรือโอน")
        tax = str(data.get("tax_id", ""))
        require(not tax or re.fullmatch(r"\d{13}", tax), "เลขผู้เสียภาษีต้องมี 13 หลัก")
        bill = payable(job, at)
        paid = money(data.get("paid"))
        require(paid >= bill["total"], "ต้องรับเงินครบก่อนคืนเครื่อง")
        receipt = dict(
            id=receipt_id or sequence(db, "RC", at),
            at=at.isoformat(),
            bill=bill,
            paid=paid,
            change=paid - bill["total"],
            receiver=str(data["receiver"])[:200],
            method=data["method"],
            company=str(data.get("company", ""))[:500],
            tax_id=tax,
        )
        job["receipt"] = receipt
        job["returned_at"] = at.isoformat()
        job["storage_paid"] = bill["storage"]
        job.pop("passcode", None)
        change(job, STATUSES[8], at, actor)
    elif kind == "void_receipt":
        allowed(user, "owner")
        require(
            job.get("receipt") and not job["receipt"].get("void"),
            "ไม่มีใบเสร็จที่ยกเลิกได้",
        )
        require(bool(data.get("reason")), "ต้องระบุเหตุผล")
        job["receipt"]["void"] = str(data["reason"])
        audit(job, at, actor, "ยกเลิกใบเสร็จ: " + str(data["reason"]))
        for row in db.execute("SELECT data FROM jobs").fetchall():
            other = json.loads(row[0])
            if (
                other["id"] != job["id"]
                and other.get("receipt", {}).get("id") == job["receipt"]["id"]
            ):
                other["receipt"]["void"] = str(data["reason"])
                audit(other, at, actor, "ยกเลิกใบเสร็จรวม: " + str(data["reason"]))
                save(db, other)
    else:
        raise ValueError("ไม่รู้จักคำสั่ง")
    save(db, job)


class Handler(BaseHTTPRequestHandler):
    server_version = "Somdee/1.0"

    def log_message(self, format, *args):
        # Do not log customer identifiers or credentials.
        print(
            self.command
            + " "
            + urlparse(self.path).path
            + " "
            + str(args[1] if len(args) > 1 else ""),
            flush=True,
        )

    def send(self, status, payload, cookie=None):
        raw = encode(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(raw)

    def body(self):
        length = int(self.headers.get("Content-Length", "0"))
        require(0 < length <= 18_000_000, "คำขอใหญ่เกินไป")
        data = json.loads(self.rfile.read(length))
        require(isinstance(data, dict), "รูปแบบข้อมูลไม่ถูกต้อง")
        return data

    def user(self, db):
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        token = cookie.get("shop_session")
        if not token:
            return None
        row = db.execute(
            "SELECT u.id,u.name,u.role FROM sessions s JOIN users u ON s.user_id=u.id WHERE s.token=? AND s.expires>? AND u.active=1",
            (
                hashlib.sha256(token.value.encode()).hexdigest(),
                datetime.now(TZ).isoformat(),
            ),
        ).fetchone()
        return dict(row) if row else None

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            return self.api("GET", path)
        files = {
            "/": "index.html",
            "/track": "index.html",
            "/app.js": "app.js",
            "/style.css": "style.css",
            "/vendor/qrcode.js": "vendor/qrcode.js",
            "/fonts/NotoSansThai-Regular.ttf": "fonts/NotoSansThai-Regular.ttf",
            "/fonts/NotoSansThai-Bold.ttf": "fonts/NotoSansThai-Bold.ttf",
        }
        if path not in files:
            return self.send(404, dict(error="ไม่พบหน้า"))
        raw = (ROOT / "static" / files[path]).read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type",
            {
                "html": "text/html; charset=utf-8",
                "js": "text/javascript; charset=utf-8",
                "css": "text/css; charset=utf-8",
                "ttf": "font/ttf",
            }[files[path].split(".")[-1]],
        )
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        self.api("POST", urlparse(self.path).path)

    def api(self, method, path):
        try:
            if method == "POST":
                require(
                    self.headers.get("Content-Type", "").split(";")[0]
                    == "application/json",
                    "ต้องส่ง JSON",
                )
                origin = self.headers.get("Origin")
                require(
                    not origin or urlparse(origin).netloc == self.headers.get("Host"),
                    "Origin ไม่ถูกต้อง",
                )
                data = self.body()
            else:
                data = {}
            with LOCK, connect() as db:
                maintain(db)
                user = self.user(db)
                at = now(db)
                if path == "/api/login" and method == "POST":
                    key = "login:" + self.client_address[0]
                    limit = db.execute(
                        "SELECT * FROM attempts WHERE key=?", (key,)
                    ).fetchone()
                    if (
                        limit
                        and limit["count"] >= 10
                        and datetime.now(TZ) < datetime.fromisoformat(limit["until"])
                    ):
                        return self.send(429, dict(error="ลองใหม่ใน 15 นาที"))
                    email = str(data.get("email", "")).lower()
                    id = email.removesuffix("@somdee.test")
                    row = db.execute(
                        "SELECT * FROM users WHERE id=? AND active=1", (id,)
                    ).fetchone()
                    if not row or not verify(data.get("password", ""), row["hash"]):
                        count = (
                            limit["count"]
                            if limit
                            and datetime.now(TZ)
                            < datetime.fromisoformat(limit["until"])
                            else 0
                        ) + 1
                        db.execute(
                            "INSERT OR REPLACE INTO attempts VALUES (?,?,?)",
                            (
                                key,
                                count,
                                (datetime.now(TZ) + timedelta(minutes=15)).isoformat(),
                            ),
                        )
                        db.commit()
                        return self.send(401, dict(error="บัญชีหรือรหัสผ่านไม่ถูกต้อง"))
                    db.execute("DELETE FROM attempts WHERE key=?", (key,))
                    token = secrets.token_urlsafe(32)
                    db.execute(
                        "INSERT INTO sessions VALUES (?,?,?)",
                        (
                            hashlib.sha256(token.encode()).hexdigest(),
                            id,
                            (datetime.now(TZ) + timedelta(hours=8)).isoformat(),
                        ),
                    )
                    db.commit()
                    return self.send(
                        200,
                        dict(ok=True),
                        f"shop_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800"
                        + (
                            "; Secure"
                            if os.environ.get("SHOP_SECURE_COOKIE") == "1"
                            else ""
                        ),
                    )
                if path == "/api/logout" and method == "POST":
                    cookie = SimpleCookie()
                    cookie.load(self.headers.get("Cookie", ""))
                    if cookie.get("shop_session"):
                        db.execute(
                            "DELETE FROM sessions WHERE token=?",
                            (
                                hashlib.sha256(
                                    cookie["shop_session"].value.encode()
                                ).hexdigest(),
                            ),
                        )
                    db.commit()
                    return self.send(
                        200,
                        dict(ok=True),
                        "shop_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0",
                    )
                if path == "/api/track" and method == "POST":
                    id = str(data.get("id", "")).strip().upper()
                    key = "track:" + id
                    limit = db.execute(
                        "SELECT * FROM attempts WHERE key=?", (key,)
                    ).fetchone()
                    if (
                        limit
                        and limit["until"]
                        and at < datetime.fromisoformat(limit["until"])
                    ):
                        return self.send(
                            429, dict(error="เลขใบรับถูกล็อก 15 นาที กรุณาติดต่อร้าน")
                        )
                    row = db.execute(
                        "SELECT data FROM jobs WHERE id=?", (id,)
                    ).fetchone()
                    job = json.loads(row[0]) if row else None
                    if not job or not hmac.compare_digest(
                        str(data.get("last4", "")), job["phone"][-4:]
                    ):
                        count = limit["count"] if limit and not limit["until"] else 0
                        count += 1
                        until = (
                            (at + timedelta(minutes=15)).isoformat()
                            if count >= 5
                            else ""
                        )
                        db.execute(
                            "INSERT OR REPLACE INTO attempts VALUES (?,?,?)",
                            (key, count, until),
                        )
                        db.commit()
                        return self.send(
                            400, dict(error="เลขใบรับหรือเบอร์ 4 ตัวท้ายไม่ถูกต้อง")
                        )
                    db.execute("DELETE FROM attempts WHERE key=?", (key,))
                    if "accept" in data:
                        require(type(data["accept"]) is bool, "คำตอบไม่ถูกต้อง")
                        respond(
                            db, job, data["accept"], bool(data.get("rush")), "ลูกค้า"
                        )
                        save(db, job)
                    db.commit()
                    return self.send(200, public_job(job, at))
                if not user:
                    return self.send(401, dict(error="กรุณาเข้าสู่ระบบ"))
                if path == "/api/bootstrap" and method == "GET":
                    jobs = [
                        json.loads(row[0])
                        for row in db.execute(
                            "SELECT data FROM jobs ORDER BY rowid DESC"
                        )
                    ]
                    if user["role"] == "tech":
                        jobs = [
                            j
                            for j in jobs
                            if j.get("assignee") == user["id"]
                            or not j.get("assignee")
                            and j["status"] == STATUSES[0]
                        ]
                    users = [
                        dict(x)
                        for x in db.execute("SELECT id,name,role,active FROM users")
                    ]
                    db.commit()
                    return self.send(
                        200,
                        dict(
                            user=user,
                            jobs=[staff_job(j, user, at) for j in jobs],
                            statuses=STATUSES,
                            devices=DEVICES,
                            catalog=setting(db, "catalog"),
                            inspection=setting(db, "inspection"),
                            holidays=setting(db, "holidays", []),
                            users=users,
                            now=at.isoformat(),
                            test_mode=TEST_MODE,
                        ),
                    )
                if path == "/api/jobs" and method == "POST":
                    allowed(user, "owner", "front")
                    job = new_job(db, data, user["name"])
                    db.commit()
                    return self.send(201, staff_job(job, user, at))
                if path.startswith("/api/jobs/") and method == "POST":
                    job = get_job(db, path.rsplit("/", 1)[-1])
                    action(db, job, data, user)
                    db.commit()
                    return self.send(200, staff_job(job, user, at))
                if path == "/api/checkout" and method == "POST":
                    allowed(user, "owner", "front")
                    ids = data.get("ids")
                    require(
                        isinstance(ids, list)
                        and 1 <= len(ids) <= 20
                        and len(set(ids)) == len(ids),
                        "เลือกใบรับ 1–20 ใบ ไม่ซ้ำกัน",
                    )
                    jobs = [get_job(db, id) for id in ids]
                    require(
                        all(j["phone"] == jobs[0]["phone"] for j in jobs),
                        "ใบรับรวมต้องเป็นของผู้จ่ายเงินคนเดียวกัน",
                    )
                    total = sum(payable(j, at)["total"] for j in jobs)
                    paid = money(data.get("paid"))
                    require(paid >= total, "ต้องรับเงินครบทุกเครื่องก่อนคืน")
                    receipt_id = sequence(db, "RC", at)
                    for job in jobs:
                        payment = dict(
                            data, action="checkout", paid=payable(job, at)["total"]
                        )
                        action(db, job, payment, user, receipt_id=receipt_id)
                    combined = [
                        dict(id=j["id"], model=j["model"], bill=j["receipt"]["bill"])
                        for j in jobs
                    ]
                    for job in jobs:
                        job["receipt"].update(
                            combined=combined,
                            combined_paid=paid,
                            combined_change=paid - total,
                        )
                        save(db, job)
                    db.commit()
                    return self.send(200, dict(ok=True, receipt_id=receipt_id))
                if path == "/api/unlock" and method == "POST":
                    allowed(user, "owner", "front")
                    db.execute(
                        "DELETE FROM attempts WHERE key=?",
                        ("track:" + str(data.get("id", "")),),
                    )
                    db.commit()
                    return self.send(200, dict(ok=True))
                if path == "/api/claim-deny" and method == "POST":
                    allowed(user, "owner")
                    job = get_job(db, data.get("id"))
                    require(
                        job.get("claim_of") and job["status"] in STATUSES[:2],
                        "ปฏิเสธเคลมได้ก่อนเสนอราคาเท่านั้น",
                    )
                    require(bool(data.get("reason")), "ต้องระบุเหตุผล")
                    audit(job, at, user["name"], "เคลมไม่ได้: " + str(data["reason"]))
                    job["claim_denied_of"] = job.pop("claim_of")
                    job["inspection_fee"] = setting(db, "inspection")[job["device"]]
                    save(db, job)
                    db.commit()
                    return self.send(200, staff_job(job, user, at))
                if path == "/api/settings" and method == "POST":
                    allowed(user, "owner")
                    holidays = data.get("holidays", [])
                    require(
                        isinstance(holidays, list) and len(holidays) <= 365,
                        "วันหยุดไม่ถูกต้อง",
                    )
                    for d in holidays:
                        date.fromisoformat(d)
                    set_setting(db, "holidays", holidays)
                    if "inspection" in data:
                        require(
                            set(data["inspection"]) == set(DEVICES),
                            "ต้องมีค่าตรวจครบ 4 ประเภท",
                        )
                        set_setting(
                            db,
                            "inspection",
                            {k: money(v) for k, v in data["inspection"].items()},
                        )
                    if "catalog" in data:
                        catalog = data["catalog"]
                        require(
                            isinstance(catalog, list)
                            and len(catalog) == 9
                            and [x["code"] for x in catalog]
                            == [x["code"] for x in CATALOG],
                            "ตารางราคาไม่ถูกต้อง",
                        )
                        for item in catalog:
                            money(item["labor"])
                            require(item["warranty"] in (0, 30, 90), "ประกันไม่ถูกต้อง")
                            require(
                                type(item["days"]) is int and 1 <= item["days"] <= 365,
                                "จำนวนวันไม่ถูกต้อง",
                            )
                            original = next(
                                x for x in CATALOG if x["code"] == item["code"]
                            )
                            item["name"] = original["name"]
                            item["types"] = original["types"]
                        set_setting(db, "catalog", catalog)
                    db.commit()
                    return self.send(200, dict(ok=True))
                if path == "/api/users" and method == "POST":
                    allowed(user, "owner")
                    id = str(data.get("id", ""))
                    require(
                        re.fullmatch("[a-z][a-z0-9]{1,30}", id),
                        "รหัสบัญชีใช้ a-z และ 0-9",
                    )
                    existing = db.execute(
                        "SELECT * FROM users WHERE id=?", (id,)
                    ).fetchone()
                    require(
                        id != user["id"] or data.get("active", True),
                        "ปิดบัญชีตัวเองไม่ได้",
                    )
                    active = bool(data.get("active", True))
                    if not active:
                        require(
                            not any(
                                json.loads(r[0]).get("assignee") == id
                                and json.loads(r[0])["status"] != STATUSES[8]
                                for r in db.execute("SELECT data FROM jobs")
                            ),
                            "ต้องมอบงานซ่อมค้างให้คนอื่นก่อน",
                        )
                    role = data.get("role", existing["role"] if existing else "front")
                    require(role in ("owner", "front", "tech"), "ตำแหน่งไม่ถูกต้อง")
                    require(
                        existing is None or role == existing["role"],
                        "เปลี่ยนตำแหน่งบัญชีเดิมไม่ได้",
                    )
                    require(
                        role != "tech" or id in SKILLS,
                        "รุ่นนี้รองรับบัญชีช่าง boy / bank / em ตามตารางทักษะ",
                    )
                    ph = (
                        password_hash(data["password"])
                        if data.get("password")
                        else existing["hash"] if existing else None
                    )
                    require(bool(ph), "ต้องตั้งรหัสผ่าน")
                    name = str(
                        data.get("name", existing["name"] if existing else "")
                    ).strip()
                    require(bool(name), "ต้องระบุชื่อ")
                    db.execute(
                        "INSERT OR REPLACE INTO users VALUES (?,?,?,?,?)",
                        (id, name[:100], role, ph, int(active)),
                    )
                    db.execute("DELETE FROM sessions WHERE user_id=?", (id,))
                    db.commit()
                    return self.send(200, dict(ok=True))
                if path == "/api/claim" and method == "POST":
                    allowed(user, "owner", "front")
                    original = get_job(db, data.get("id"))
                    require(
                        original["status"] == STATUSES[8], "ต้องเป็นใบที่คืนเครื่องแล้ว"
                    )
                    warranties = staff_job(original, user, at)["warranties"]
                    index = data.get("item")
                    require(
                        type(index) is int
                        and 0 <= index < len(warranties)
                        and warranties[index]["eligible"],
                        "รายการนี้พ้นประกันหรือไม่มีประกัน",
                    )
                    intake = data.get("intake", {})
                    intake.update(
                        {
                            k: original[k]
                            for k in (
                                "name",
                                "phone",
                                "device",
                                "model",
                                "line",
                                "accessories",
                            )
                        }
                    )
                    job = new_job(db, intake, user["name"])
                    job["claim_of"] = original["id"]
                    job["claim_item"] = index
                    job["warranty_origin_at"] = (
                        original.get("warranty_origin_at") or original["returned_at"]
                    )
                    job["inspection_fee"] = 0
                    save(db, job)
                    db.commit()
                    return self.send(201, staff_job(job, user, at))
                if path == "/api/test" and method == "POST":
                    require(TEST_MODE, "เครื่องมือทดสอบปิดอยู่")
                    allowed(user, "owner")
                    if data.get("now"):
                        datetime.fromisoformat(data["now"])
                        set_setting(db, "test_now", data["now"])
                    if data.get("reset"):
                        seed(db)
                    db.commit()
                    return self.send(200, dict(ok=True))
                self.send(404, dict(error="ไม่พบ API"))
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            self.send(400, dict(error=str(exc)))
        except (BrokenPipeError, ConnectionResetError):
            # Browser navigation can close a socket after a committed mutation.
            return
        except Exception:
            import traceback

            traceback.print_exc()
            self.send(500, dict(error="ระบบขัดข้อง กรุณาลองอีกครั้ง"))


def seed(db):
    at = now(db)
    db.execute("DELETE FROM jobs")
    db.execute("DELETE FROM counters")
    db.execute("DELETE FROM attempts")
    names = [
        "น้องเจ",
        "คุณฝ้าย",
        "ลุงสมชาย",
        "คุณบี",
        "คุณบี",
        "เจ๊หงส์",
        "เจ๊หงส์",
        "น้องเจ",
        "คุณฝ้าย",
    ]
    phones = [
        "0811112201",
        "0892223302",
        "0863334403",
        "0624445504",
        "0624445504",
        "0855556605",
        "0855556605",
        "0811112201",
        "0892223302",
    ]
    devices = ["D01", "D01", "D03", "D01", "D02", "D04", "D04", "D02", "D03"]
    models = [
        "Acer Aspire",
        "Lenovo ThinkPad",
        "Samsung Galaxy",
        "ASUS VivoBook",
        "PC Desktop",
        "Epson L3110",
        "Canon G2010",
        "PC Desktop",
        "iPhone 13",
    ]
    states = [2, 3, 1, 8, 8, 5, 5, 4, 3]
    codes = ["R03", "R01", "R02", "R02", "R05", "R07", "R08", "R03", "R01"]
    for i in range(9):
        item = dict(next(x for x in CATALOG if x["code"] == codes[i]))
        item = {k: item[k] for k in ("code", "name", "labor", "warranty")}
        item["parts"] = 1290 if i == 0 else 3200 if i == 1 else 0
        sent = at - timedelta(days=7 if i == 0 else 2)
        q = dict(
            version=1,
            items=[item],
            days=1,
            total=item["labor"] + item["parts"],
            sent_at=sent.isoformat(),
            notified_at=sent.isoformat(),
            rush_eligible=True,
            data_loss=False,
        )
        if i != 0:
            q.update(
                decision="accepted", responded_at=(at - timedelta(hours=23)).isoformat()
            )
        job = dict(
            id=f"SD-TEST-{i+1:03d}",
            created_at=sent.isoformat(),
            name=names[i],
            phone=phones[i],
            device=devices[i],
            model=models[i],
            symptom="เครื่องมีปัญหา ต้องการตรวจเช็ก",
            accessories="ตัวเครื่องและสายชาร์จ",
            line="" if i == 2 else "@customer",
            serial="",
            notes="",
            passcode="demo-device-code",
            consent=True,
            photos=[],
            status=STATUSES[states[i]],
            assignee=(
                "em"
                if devices[i] == "D04"
                else "bank" if devices[i] == "D03" else "boy"
            ),
            quotes=[] if i == 2 else [q],
            timeline=[],
            notifications=[],
            rush=i == 1,
            inspection_fee=200 if devices[i] == "D03" else 300,
        )
        if i != 0 and i != 2:
            job.update(current_items=[item], accepted_base=q["total"])
        if i == 1:
            job["deadline"] = (at + timedelta(hours=1)).isoformat()
        if i in (3, 4):
            job["returned_at"] = (at - timedelta(days=90 if i == 3 else 31)).isoformat()
            job.pop("passcode")
        if i in (5, 6):
            job["notified_at"] = (at - timedelta(days=60 if i == 5 else 65)).isoformat()
            job["current_items"] = []
        if i in (7, 8):
            job["pickup"] = (
                (at + timedelta(days=-1 if i == 7 else 1)).date().isoformat()
            )
        audit(job, sent, "ระบบ", "ข้อมูลตัวอย่าง", True)
        save(db, job)


def main():
    init()
    host = os.environ.get("SHOP_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"ซ่อมดี IT Service: http://{host}:{port}", flush=True)
    stop = threading.Event()

    def scheduled():
        while not stop.wait(30):
            try:
                with LOCK, connect() as db:
                    maintain(db)
            except Exception:
                import traceback

                traceback.print_exc()

    threading.Thread(target=scheduled, daemon=True).start()
    http = ThreadingHTTPServer((host, port), Handler)
    try:
        http.serve_forever()
    finally:
        stop.set()
        http.server_close()


if __name__ == "__main__":
    main()
