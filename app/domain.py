"""Deterministic shop rules. All amounts are integer Thai baht."""

from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import math

TZ = ZoneInfo("Asia/Bangkok")
STATUSES = [
    "รับเครื่องแล้ว รอตรวจ",
    "กำลังตรวจ",
    "รอลูกค้ายืนยันราคา",
    "กำลังซ่อม",
    "รออะไหล่",
    "ซ่อมเสร็จ รอรับเครื่อง",
    "ลูกค้าไม่ซ่อม รอรับเครื่องคืน",
    "ซ่อมไม่ได้ รอรับเครื่องคืน",
    "รับเครื่องคืนแล้ว",
]
DEVICES = {
    "D01": "โน้ตบุ๊ก",
    "D02": "คอมพิวเตอร์ตั้งโต๊ะ (PC)",
    "D03": "มือถือ / แท็บเล็ต",
    "D04": "ปริ้นเตอร์",
}
CATALOG = [
    dict(code=c, name=n, types=t.split(","), labor=l, days=d, warranty=w)
    for c, n, t, l, d, w in [
        ("R01", "เปลี่ยนจอ", "D01,D03", 500, 2, 90),
        ("R02", "เปลี่ยนแบตเตอรี่", "D01,D03", 300, 1, 90),
        ("R03", "เปลี่ยน SSD / RAM", "D01,D02", 300, 1, 90),
        ("R04", "ซ่อมเมนบอร์ด", "D01,D02,D03", 1200, 5, 90),
        ("R05", "ลงวินโดวส์ใหม่", "D01,D02", 500, 1, 30),
        ("R06", "ล้างเครื่อง ทำความสะอาด เปลี่ยนซิลิโคน", "D01,D02", 350, 1, 30),
        ("R07", "ล้างหัวพิมพ์", "D04", 400, 1, 30),
        ("R08", "เปลี่ยนชุดดึงกระดาษ", "D04", 450, 2, 90),
        ("R09", "กู้ข้อมูล", "D01,D02,D03", 1500, 3, 0),
    ]
]
SKILLS = {"boy": ["D01", "D02"], "bank": ["D03"], "em": ["D01", "D02", "D04"]}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def money(value):
    require(
        type(value) is int and 0 <= value <= 100_000_000,
        "ยอดเงินต้องเป็นบาทเต็ม ตั้งแต่ 0 ถึง 100,000,000",
    )
    return value


def working_day(day, device, holidays=()):
    return (
        day.weekday() != 6
        and not (device == "D04" and day.weekday() == 0)
        and day.isoformat() not in holidays
    )


def pickup(start, days, device, holidays=()):
    require(type(days) is int and 1 <= days <= 365, "จำนวนวันทำการต้องเป็น 1–365 วัน")
    result = start.date()
    while days:
        result += timedelta(days=1)
        if working_day(result, device, holidays):
            days -= 1
    return result.isoformat()


def rush_deadline(start, holidays=()):
    result = start + timedelta(hours=24)
    if (
        result.weekday() == 6
        or result.date().isoformat() in holidays
        or result.time() > time(19)
    ):
        result = datetime.combine(result.date() + timedelta(days=1), time(10), TZ)
    elif result.time() < time(10):
        result = datetime.combine(result.date(), time(10), TZ)
    while result.weekday() == 6 or result.date().isoformat() in holidays:
        result += timedelta(days=1)
    return result.isoformat()


def rush_fee(labor):
    return math.ceil(labor * 1.5 / 10) * 10 - labor


def storage(notified, now):
    return (
        max(0, (now.date() - datetime.fromisoformat(notified).date()).days - 60) * 20
        if notified
        else 0
    )


def quote_items(items, device, catalog=CATALOG):
    require(
        isinstance(items, list) and 1 <= len(items) <= 30,
        "ต้องมีรายการซ่อม 1–30 รายการ",
    )
    result = []
    for raw in items:
        code = raw.get("code", "CUSTOM")
        base = next((x for x in catalog if x["code"] == code), None)
        require(
            code == "CUSTOM" or (base and device in base["types"]),
            "รายการซ่อมไม่ตรงประเภทเครื่อง",
        )
        labor = money(raw.get("labor", base["labor"] if base else 0))
        if base:
            require(
                labor == base["labor"] or code == "R09" and labor >= base["labor"],
                "ค่าแรงไม่ตรงตารางราคา",
            )
        warranty = base["warranty"] if base else raw.get("warranty", 90)
        require(warranty in (0, 30, 90), "ประกันต้องเป็น 0 / 30 / 90 วัน")
        name = base["name"] if base else str(raw.get("name", "")).strip()
        require(bool(name) and len(name) <= 200, "กรุณาระบุชื่อรายการซ่อม")
        result.append(
            dict(
                code=code,
                name=name,
                labor=labor,
                parts=money(raw.get("parts", 0)),
                warranty=warranty,
            )
        )
    return result


def payable(job, now):
    fee = (
        storage(job.get("notified_at"), now)
        if job["status"] in STATUSES[5:8]
        else job.get("storage_paid", 0)
    )
    q = job.get("quotes", [])
    quote = q[-1] if q else {}
    items = job.get("current_items", quote.get("items", []))
    labor = sum(x["labor"] for x in items)
    parts = sum(x["parts"] for x in items)
    inspection = job.get("inspection_fee", 200 if job["device"] == "D03" else 300)
    rush = rush_fee(labor) if job.get("rush") else 0
    if job.get("rush_late") and not job.get("restore_rush"):
        rush = 0
    discount = job.get("discount", 0)
    if job.get("manual_charges") is not None:
        charges = job["manual_charges"]
        labor = charges["labor"]
        parts = charges["parts"]
        inspection = charges["inspection"]
        rush = 0
        total = max(0, labor + parts + inspection - discount) + fee
        credit = 0
    elif job.get("closing_reason") in ("rejected_first", "expired_first"):
        labor = parts = rush = 0
        credit = 0
        total = max(0, inspection - discount) + fee
    elif job.get("closing_reason") in ("unrepairable", "failed"):
        labor = parts = rush = inspection = credit = 0
        total = fee
    else:
        credit = inspection
        total = max(0, labor + parts + rush - discount - credit) + fee
    return dict(
        labor=labor,
        parts=parts,
        rush=rush,
        inspection=inspection,
        credit=credit,
        discount=discount,
        storage=fee,
        total=total,
    )
