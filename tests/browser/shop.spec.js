const { test, expect } = require("@playwright/test");
async function login(page, id = "owner") {
  await page.goto("/");
  await page.getByLabel("บัญชีพนักงาน").fill(id + "@somdee.test");
  await page.getByLabel("รหัสผ่าน", { exact: true }).fill("browser-test-123");
  await page.getByRole("button", { name: "เข้าสู่ระบบ →" }).click();
  await expect(page.getByRole("heading", { name: "ภาพรวมร้าน" })).toBeVisible();
}
test.beforeEach(async ({ request }) => {
  await request.post("/api/login", {
    data: { email: "owner@somdee.test", password: "browser-test-123" },
  });
  await request.post("/api/settings", { data: { holidays: [] } });
  await request.post("/api/test", {
    data: { now: "2026-11-11T12:00", reset: true },
  });
});
test("staff can navigate, search, quote, collect payment, and print", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  await page
    .getByRole("button", { name: "งานซ่อมทั้งหมด", exact: true })
    .click();
  await page.getByRole("textbox", { name: "ค้นหางานซ่อม" }).fill("ลุงสมชาย");
  await expect(
    page.getByRole("button", { name: "SD-TEST-003", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "SD-TEST-003", exact: true }).click();
  await page
    .getByRole("button", { name: "สร้างใบเสนอราคา", exact: true })
    .click();
  await page.getByLabel("รายการซ่อม", { exact: true }).selectOption("R02");
  await page.getByLabel("ค่าอะไหล่", { exact: true }).fill("500");
  await page
    .getByRole("button", { name: "ส่งใบเสนอราคา", exact: true })
    .click();
  await expect(page.getByText("ฉบับที่ 1", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "โทรแจ้งแล้ว", exact: true })
    .last()
    .click();
  await page.getByRole("button", { name: "บันทึกคำตอบทางโทรศัพท์" }).click();
  await page.getByRole("button", { name: "บันทึกคำตอบ", exact: true }).click();
  await page.getByRole("button", { name: "ซ่อมเสร็จ", exact: true }).click();
  await page
    .getByRole("button", { name: "รับเงินและคืนเครื่อง", exact: true })
    .click();
  await page.getByLabel("เบอร์ลูกค้า 4 ตัวท้าย").fill("4403");
  await page.getByRole("button", { name: "รับเงินครบและคืนเครื่อง" }).click();
  await expect(
    page.getByRole("button", { name: "พิมพ์ใบเสร็จ", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "พิมพ์ใบเสร็จ", exact: true }).click();
  await expect(
    page.getByText("รับเครื่องคืนแล้ว", { exact: true }).first(),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
test("customer mobile tracking and confirmation with no sensitive data", async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/track");
  await page.getByLabel("เลขใบรับ", { exact: true }).fill("SD-TEST-001");
  await page.getByLabel("เบอร์โทร 4 ตัวท้าย").fill("2201");
  await page.getByRole("button", { name: "เช็กสถานะ →" }).click();
  await expect(
    page.getByRole("button", { name: "ยืนยันแบบปกติ", exact: true }),
  ).toBeVisible();
  expect(await page.locator("body").innerText()).not.toContain(
    "demo-device-code",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "ยืนยันแบบปกติ", exact: true })
    .click();
  await page.getByRole("button", { name: "ยืนยันคำตอบ" }).click();
  await expect(
    page.getByText("กำลังซ่อม", { exact: true }).first(),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/customer-mobile.png",
    fullPage: true,
  });
});
test("technician mobile and owner settings", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await login(page, "boy");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "งานซ่อมทั้งหมด", exact: true })
    .click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "ออก", exact: true }).click();
  await login(page);
  await page.getByRole("button", { name: "ตั้งค่าร้าน", exact: true }).click();
  await page.getByLabel("วันที่หยุด").fill("2026-11-12");
  await page.getByRole("button", { name: "บันทึกวันหยุด" }).click();
  await expect(page.getByLabel("วันที่หยุด")).toHaveValue("2026-11-12");
});
test("intake validates photos, saves and prints QR without code exposure", async ({
  page,
}) => {
  await login(page);
  await page
    .getByRole("button", { name: "＋ รับเครื่องใหม่", exact: true })
    .click();
  await page.getByLabel("ชื่อลูกค้า").fill("ลูกค้า ทดสอบ");
  await page.getByLabel("เบอร์โทร *", { exact: true }).fill("0812345678");
  await page.getByLabel("ยี่ห้อ / รุ่นเครื่อง").fill("Test laptop");
  await page.getByLabel("อาการเสีย").fill("เปิดไม่ติด");
  await page.getByLabel("อุปกรณ์ที่ฝาก").fill("ไม่มี");
  await page
    .getByLabel("ให้ลูกค้าพิมพ์รหัสเครื่อง")
    .fill("private-device-pass");
  await page.getByLabel("ลูกค้ารับทราบและยอมรับความเสี่ยง").check();
  const photo = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII=",
    "base64",
  );
  await page.getByLabel("รูปสภาพเครื่อง", { exact: true }).setInputFiles([
    { name: "front.png", mimeType: "image/png", buffer: photo },
    { name: "back.png", mimeType: "image/png", buffer: photo },
  ]);
  await page.getByRole("button", { name: "บันทึกใบรับ →" }).click();
  await expect(
    page.getByRole("heading", { name: "SD-261111-001", exact: true }),
  ).toBeVisible();
  await page.evaluate(
    () =>
      (window.print = () => {
        window.printedText = document.body.innerText;
        window.qrFound = !!document.querySelector("#receipt-qr svg");
      }),
  );
  await page.getByRole("button", { name: "พิมพ์ใบรับ", exact: true }).click();
  expect(await page.evaluate(() => window.printedText)).not.toContain(
    "private-device-pass",
  );
  expect(await page.evaluate(() => window.qrFound)).toBe(true);
  await page.screenshot({
    path: "test-results/staff-desktop.png",
    fullPage: true,
  });
});
