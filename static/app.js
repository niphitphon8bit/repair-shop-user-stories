"use strict";
const $ = (s) => document.querySelector(s),
  root = $("#app");
let state,
  page = "dashboard",
  selected = null,
  filter = "",
  query = "",
  trackCredentials = null,
  trackResult = null;
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const baht = (n) => "฿" + Number(n || 0).toLocaleString("th-TH");
const dt = (v) =>
  v
    ? new Date(v).toLocaleString("th-TH", {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "—";
const day = (v) =>
  v
    ? new Date(v.slice(0, 10) + "T12:00:00+07:00").toLocaleDateString("th-TH", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "ยังไม่กำหนด";
const field = (name, label, type = "text", value = "", extra = "") =>
  `<label>${label}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;
const check = (name, label, checked = false) =>
  `<label class="check"><input name="${name}" type="checkbox" ${checked ? "checked" : ""}>${label}</label>`;
const button = (action, label, cls = "", extra = "") =>
  `<button data-action="${action}" class="${cls}" ${extra}>${label}</button>`;
const brand = () =>
  '<div class="brand"><div class="logo">↗</div><div><strong>ซ่อมดี</strong><small>IT SERVICE & REPAIR</small></div></div>';
async function api(path, data) {
  const response = await fetch(path, {
    method: data ? "POST" : "GET",
    headers: data ? { "Content-Type": "application/json" } : {},
    body: data ? JSON.stringify(data) : undefined,
  });
  const value = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path != "/api/login") {
      state = null;
      renderLogin();
    }
    throw Error(value.error || "ทำรายการไม่สำเร็จ");
  }
  return value;
}
function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.style.display = "block";
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (el.style.display = "none"), 4500);
}
function formData(form) {
  const values = Object.fromEntries(new FormData(form));
  form
    .querySelectorAll("input[type=checkbox]")
    .forEach((x) => (values[x.name] = x.checked));
  return values;
}
function modal(title, body) {
  const el = $("#modal");
  el.innerHTML = `<div class="panel-title"><h2>${title}</h2>${button("close", "✕", "quiet", 'aria-label="ปิดหน้าต่าง"')}</div>${body}<div class="error" role="alert" id="modal-error"></div>`;
  el.showModal();
}
function closeModal() {
  if ($("#modal").open) $("#modal").close();
}
function statusBadge(j) {
  const i = state ? state.statuses.indexOf(j.status) : -1;
  const cls =
    i === 5 || i === 8
      ? "green"
      : i === 2 || i === 4
        ? "yellow"
        : i === 6 || i === 7
          ? "red"
          : "blue";
  return `<span class="badge ${cls}"><span class="dot"></span>${esc(j.status)}</span>`;
}
async function refresh() {
  state = await api("/api/bootstrap");
  render();
}
function renderLogin() {
  root.innerHTML = `<div class="login-page"><div class="login-art"><div class="eyebrow">SOMDEE • REPAIR MANAGEMENT</div><h1>ทุกงานซ่อม<br>ดูแลอย่างเข้าใจ</h1><p>รับเครื่อง ติดตามงาน และส่งคืนความสบายใจ<br>พื้นที่ทำงานของทีมซ่อมดี IT Service</p><small>ดูแลงานเล็ก ๆ ให้เป็นเรื่องง่าย ตั้งแต่ต้นจนจบ</small></div><div class="login-form"><div>${brand()}<h1>ยินดีต้อนรับกลับ</h1><p class="muted">เข้าสู่ระบบเพื่อจัดการงานซ่อมของคุณ</p><form id="login-form">${field("email", "บัญชีพนักงาน", "email", "", 'required placeholder="owner@somdee.test" autocomplete="username"')}${field("password", "รหัสผ่าน", "password", "", 'required autocomplete="current-password"')}<div class="error" id="login-error" role="alert"></div><button class="primary" type="submit">เข้าสู่ระบบ →</button></form><p class="footer-note">สำหรับทีมงานร้านซ่อมดี</p><a href="/track">เป็นลูกค้า? เช็กสถานะงานซ่อม ↗</a></div></div></div>`;
}
const navItems = [
  ["dashboard", "▦", "ภาพรวมร้าน"],
  ["jobs", "▤", "งานซ่อมทั้งหมด"],
  ["new", "＋", "รับเครื่องใหม่"],
  ["calls", "♧", "แจ้งลูกค้า"],
  ["reports", "◷", "รายงานร้าน"],
  ["settings", "⚙", "ตั้งค่าร้าน"],
];
function render() {
  if (!state) return renderLogin();
  const u = state.user;
  const nav = navItems.filter(
    ([id]) =>
      u.role === "owner" ||
      (u.role === "front"
        ? !["reports", "settings"].includes(id)
        : ["dashboard", "jobs"].includes(id)),
  );
  const title =
    (navItems.find((x) => x[0] === page) || [])[2] || "รายละเอียดงานซ่อม";
  root.innerHTML = `<div class="shell"><aside class="sidebar">${brand()}<div class="eyebrow muted">WORKSPACE</div><nav class="nav">${nav.map(([id, icon, label]) => button("nav", `<span class="symbol">${icon}</span>${label}`, page === id ? "active" : "", `data-page="${id}" aria-label="${label}"`)).join("")}</nav><div class="sidebar-foot"><div class="person"><div class="avatar">${esc(u.name[0])}</div><div><strong>${esc(u.name)}</strong><br><small>${u.role === "owner" ? "เจ้าของร้าน" : u.role === "front" ? "พนักงานหน้าร้าน" : "ช่างซ่อม"}</small></div></div>${button("logout", "ออกจากระบบ", "quiet")}</div></aside><main class="main"><header class="topbar"><div><small>พื้นที่ทำงาน</small> <span> / ${esc(title)}</span></div><div class="row"><span>● ร้านเปิด จันทร์–เสาร์ 10:00–19:00</span><a href="/track" target="_blank" rel="noopener">หน้าลูกค้า ↗</a>${button("logout", "ออก", "quiet")}</div></header><div class="content">${page === "dashboard" ? dashboard() : page === "jobs" ? jobsPage() : page === "new" ? intake() : page === "detail" ? detail() : page === "calls" ? calls() : page === "reports" ? reports() : settings()}</div></main></div>`;
}
function heading(eyebrow, title, subtitle, action = "") {
  return `<div class="heading"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p class="muted">${subtitle}</p></div>${action}</div>`;
}
function dashboard() {
  const jobs = state.jobs,
    open = jobs.filter((j) => j.status !== state.statuses[8]),
    late = jobs.filter((j) => j.urgency === "late"),
    ready = jobs.filter((j) => state.statuses.slice(5, 8).includes(j.status)),
    today = state.now.slice(0, 10);
  const cash = jobs
    .filter(
      (j) =>
        j.receipt && !j.receipt.void && j.receipt.at.slice(0, 10) === today,
    )
    .reduce((s, j) => s + j.receipt.bill.total, 0);
  return (
    heading(
      "SHOP OVERVIEW",
      "ภาพรวมร้าน",
      "ทุกความคืบหน้าของงานซ่อม อยู่ที่นี่",
      state.user.role !== "tech"
        ? button("nav", "＋ รับเครื่องใหม่", "primary", 'data-page="new"')
        : "",
    ) +
    `<div class="cards">${[
      ["▤", "งานซ่อมในร้าน", open.length, "เครื่องที่กำลังดูแล"],
      ["◷", "งานซ่อมเลยนัด", late.length, "ควรติดตามเป็นลำดับแรก"],
      ["✓", "รอลูกค้ารับเครื่อง", ready.length, "พร้อมส่งคืนให้ลูกค้า"],
      ["฿", "ยอดรับเงินวันนี้", baht(cash), "จากใบเสร็จที่ยังมีผล"],
    ]
      .map(
        ([icon, label, n, sub]) =>
          `<div class="card"><span class="icon">${icon}</span><small>${label}</small><div class="number">${n}</div><small>${sub}</small></div>`,
      )
      .join(
        "",
      )}</div><div class="panel"><div class="panel-title"><h2>งานซ่อมที่กำลังดูแล <span class="pill">${open.length} รายการ</span></h2>${button("nav", "ดูทั้งหมด →", "text-link", 'data-page="jobs"')}</div>${table(open.slice(0, 8))}</div><div class="split"><div class="panel"><div class="panel-title"><h2>ต้องติดตามวันนี้</h2><span class="badge red">${late.length} งานเลยนัด</span></div>${
      late.length
        ? late
            .slice(0, 4)
            .map(
              (j) =>
                `<div class="note row"><div><strong>${esc(j.id)}</strong><br><small>${esc(j.model)} • นัด ${day(j.pickup || j.deadline)}</small></div>${button("detail", "ติดตาม →", "text-link", `data-id="${j.id}"`)}</div>`,
            )
            .join("")
        : '<div class="empty">✓ ไม่มีงานซ่อมเลยนัด</div>'
    }</div><div class="panel"><h2>ดูแลงานซ่อมอย่างต่อเนื่อง</h2><p class="muted">เช็กใบเสนอราคาที่รอยืนยัน แจ้งความคืบหน้า และติดตามเครื่องที่รอรับเกิน 60 วัน</p><div class="row"><span>รอลูกค้ายืนยันราคา</span><strong>${jobs.filter((j) => j.status === state.statuses[2]).length} งาน</strong></div><br><div class="row"><span>เครื่องรอรับเกิน 60 วัน</span><strong>${jobs.filter((j) => j.over60).length} เครื่อง</strong></div><p class="footer-note">ข้อมูล ณ ${dt(state.now)}${state.test_mode ? " • เปิดโหมดทดสอบ" : ""}</p></div></div>`
  );
}
function table(jobs) {
  if (!jobs.length)
    return '<div class="empty">ยังไม่มีงานซ่อมในรายการนี้<br><small>งานซ่อมจะแสดงที่นี่เมื่อรับเครื่องเข้าร้าน</small></div>';
  return `<div class="table-wrap"><table><thead><tr><th>เลขใบรับ / ลูกค้า</th><th>เครื่อง / อาการ</th><th>สถานะ</th><th>ผู้รับงาน</th><th>วันนัดรับ</th><th></th></tr></thead><tbody>${jobs.map((j) => `<tr><td>${button("detail", esc(j.id), "job-id", `data-id="${j.id}"`)}<br><small>${esc(j.name)} • ${esc(j.phone)}</small></td><td><strong>${esc(j.model)} ${j.rush ? '<span class="badge yellow">ด่วน</span>' : ""}</strong><small>${esc(j.symptom.slice(0, 35))}</small></td><td>${statusBadge(j)}</td><td>${esc(state.users.find((u) => u.id === j.assignee)?.name || "ยังไม่มีช่างรับ")}</td><td><span class="${j.urgency === "late" ? "badge red" : j.urgency === "soon" ? "badge yellow" : ""}">${day(j.rush ? j.deadline : j.pickup)}</span>${j.over60 ? "<br><small>รอรับเกิน 60 วัน</small>" : ""}</td><td>${button("detail", "↗", "quiet", `data-id="${j.id}" aria-label="เปิด ${j.id}"`)}</td></tr>`).join("")}</tbody></table></div>`;
}
function jobsPage() {
  return (
    heading(
      "REPAIR WORKSPACE",
      "งานซ่อมทั้งหมด",
      "ค้นหาและติดตามงานซ่อมทุกขั้นตอน",
    ) +
    `<div class="panel"><div class="toolbar"><input id="job-search" class="search" placeholder="ค้นหาเลขใบรับ ชื่อ เบอร์โทร รุ่นเครื่อง" value="${esc(query)}" aria-label="ค้นหางานซ่อม"><select id="status-filter" aria-label="กรองสถานะ"><option value="">ทุกสถานะ</option>${state.statuses.map((s) => `<option ${filter === s ? "selected" : ""}>${s}</option>`).join("")}<option value="over60" ${filter === "over60" ? "selected" : ""}>รอรับเกิน 60 วัน</option></select></div><div id="job-table">${table(filteredJobs())}</div></div>`
  );
}
function filteredJobs() {
  return state.jobs.filter(
    (j) =>
      (!filter || (filter === "over60" ? j.over60 : j.status === filter)) &&
      [j.id, j.name, j.phone, j.model].some((v) =>
        v.toLowerCase().includes(query.toLowerCase()),
      ),
  );
}
function intake(claim = null) {
  return (
    heading(
      "NEW INTAKE",
      claim ? "เปิดใบรับแบบเคลม" : "รับเครื่องใหม่",
      claim
        ? "อ้างอิงใบเดิม " + esc(claim.id)
        : "บันทึกข้อมูลให้ครบ เพื่อเริ่มดูแลเครื่องของลูกค้า",
    ) +
    `<form id="intake-form" data-claim="${claim ? esc(claim.id) : ""}" data-item="${claim ? claim.item : ""}"><div class="split"><div><div class="panel"><h2>01 ข้อมูลลูกค้าและเครื่อง</h2><div class="form-grid">${field("name", "ชื่อลูกค้า *", "text", claim?.name || "", 'required maxlength="100"')}${field("phone", "เบอร์โทร *", "tel", claim?.phone || "", 'required pattern="0[0-9]{8,9}"')}${field("line", "LINE ID", "text", claim?.line || "")}<label>ประเภทเครื่อง *<select name="device">${Object.entries(
      state.devices,
    )
      .map(
        ([id, n]) =>
          `<option value="${id}" ${claim?.device === id ? "selected" : ""}>${id} • ${n}</option>`,
      )
      .join(
        "",
      )}</select></label>${field("model", "ยี่ห้อ / รุ่นเครื่อง *", "text", claim?.model || "", "required")}${field("serial", "หมายเลขเครื่อง / IMEI")}<label class="full">อาการเสีย *<textarea name="symptom" required maxlength="1000"></textarea></label>${field("accessories", "อุปกรณ์ที่ฝาก *", "text", claim?.accessories || "", 'required placeholder="เช่น สายชาร์จ หรือ ไม่มี"')}<label>หมายเหตุ<textarea name="notes" maxlength="1000"></textarea></label></div></div><div class="panel"><h2>02 รูปสภาพเครื่อง</h2><p class="muted">แนบ 2–6 รูป • JPEG, PNG, WebP • รูปละไม่เกิน 2 MB</p><input type="file" name="photos" id="photo-files" accept="image/jpeg,image/png,image/webp" multiple required aria-label="รูปสภาพเครื่อง"><div class="photos" id="photo-preview"></div></div></div><div><div class="panel"><h2>03 การเข้าถึงและความยินยอม</h2>${field("passcode", "ให้ลูกค้าพิมพ์รหัสเครื่อง", "password", "", 'autocomplete="off" maxlength="200"')}<br>${check("no_passcode", "ลูกค้าไม่ให้รหัส และรับทราบว่าอาจตรวจเช็กไม่ครบ")}<br>${check("rush_requested", "ลูกค้าขอด่วน (รอช่างประเมินก่อน)")}<hr><p class="muted">ร้านไม่รับประกันข้อมูลในเครื่อง กรุณาสำรองข้อมูลก่อนส่งซ่อม หากจำเป็นต้องล้างเครื่อง ช่างจะแจ้งในใบเสนอราคา</p>${check("consent", "ลูกค้ารับทราบและยอมรับความเสี่ยงเรื่องข้อมูล *")}<div class="actions"><button type="submit" class="primary">บันทึกใบรับ →</button></div><div class="error" id="form-error" role="alert"></div></div><div class="note">ค่าตรวจเช็กเก็บตอนรับเครื่องคืน<br>โน้ตบุ๊ก / PC / ปริ้นเตอร์ ${baht(state.inspection.D01)}<br>มือถือ / แท็บเล็ต ${baht(state.inspection.D03)}<br><small>ใบรับแยกสำหรับเครื่องแต่ละเครื่อง</small></div></div></div></form>`
  );
}
function billHtml(b) {
  return `<div class="bill-row"><span>ค่าแรง</span><span>${baht(b.labor)}</span></div><div class="bill-row"><span>ค่าอะไหล่</span><span>${baht(b.parts)}</span></div><div class="bill-row"><span>ค่าบริการด่วน</span><span>${baht(b.rush)}</span></div>${b.credit ? `<div class="bill-row"><span>หักค่าตรวจเช็ก</span><span>−${baht(b.credit)}</span></div>` : b.inspection ? `<div class="bill-row"><span>ค่าตรวจเช็ก</span><span>${baht(b.inspection)}</span></div>` : ""}<div class="bill-row"><span>ส่วนลด</span><span>−${baht(b.discount)}</span></div><div class="bill-row"><span>ค่าฝากเครื่อง</span><span>${baht(b.storage)}</span></div><div class="bill-row total"><span>ยอดสุทธิ</span><span>${baht(b.total)}</span></div>`;
}
function timelineHtml(events) {
  return `<div class="timeline">${[...events]
    .reverse()
    .map(
      (e) =>
        `<div class="event"><p>${esc(e.text)}</p><small>${dt(e.at)}${e.actor ? " • " + esc(e.actor) : ""}</small></div>`,
    )
    .join("")}</div>`;
}
function detail() {
  const j = state.jobs.find((x) => x.id === selected);
  if (!j) return '<div class="empty">ไม่พบงานซ่อม</div>';
  const owner = state.user.role === "owner",
    front = owner || state.user.role === "front",
    tech = owner || state.user.id === j.assignee;
  const si = state.statuses.indexOf(j.status);
  let actions = "";
  if (si === 0 && (owner || state.user.role === "tech"))
    actions += button("claim", "รับงานซ่อม", "primary");
  if (tech && [1, 2, 3, 4].includes(si))
    actions += button("quote", "สร้างใบเสนอราคา", "primary");
  if (tech && si === 3) actions += button("adjust", "ปรับราคา");
  if (front && si === 2)
    actions += button("phone-response", "บันทึกคำตอบทางโทรศัพท์");
  if (tech && si === 3)
    actions +=
      button("status", "รออะไหล่", "", 'data-target="4"') +
      button("status", "ซ่อมเสร็จ", "primary", 'data-target="5"');
  if (tech && [1, 3, 4].includes(si))
    actions += button("status", "ซ่อมไม่ได้", "danger", 'data-target="7"');
  if (tech && [4, 5].includes(si))
    actions += button("status", "กลับไปกำลังซ่อม", "", 'data-target="3"');
  if (owner && j.claim_of && [0, 1].includes(si))
    actions += button("deny-claim", "เคลมไม่ได้", "danger");
  if (owner && [3, 4].includes(si))
    actions += button("cancel", "ยกเลิกงานซ่อม", "danger");
  if (front && si === 6) actions += button("reopen", "เปิดงานกลับ");
  if (front && [5, 6, 7].includes(si))
    actions += button("checkout", "รับเงินและคืนเครื่อง", "primary");
  if (owner && [5, 6, 7].includes(si))
    actions += button("charges", "ปรับยอด / ส่วนลด");
  return (
    heading(
      "REPAIR DETAIL",
      esc(j.id),
      esc(j.model),
      button("nav", "← งานซ่อมทั้งหมด", "", 'data-page="jobs"'),
    ) +
    `<div class="panel no-print"><div class="row">${statusBadge(j)}<span class="muted">เปิดใบรับ ${dt(j.created_at)}</span></div><div class="actions">${actions}</div></div><div class="split"><div><div class="panel"><div class="panel-title"><h2>ข้อมูลใบรับ</h2><div class="no-print">${button("print-intake", "พิมพ์ใบรับ")}${button("print-label", "พิมพ์ป้าย", "quiet")}</div></div><div class="form-grid"><div><small>ลูกค้า</small><p>${esc(j.name)}<br>${esc(j.phone)}<br><small>LINE: ${esc(j.line || "ไม่มี")}</small></p></div><div><small>เครื่อง</small><p>${esc(state.devices[j.device])} • ${esc(j.model)}<br><small>Serial: ${esc(j.serial || "—")}</small></p></div><div><small>อาการเสีย</small><p>${esc(j.symptom)}</p></div><div><small>อุปกรณ์ที่ฝาก</small><p>${esc(j.accessories)}</p></div><div><small>วันนัดรับ</small><p>${day(j.pickup)}${j.rush ? "<br>กำหนดคืนด่วน: " + dt(j.deadline) : ""}</p></div><div><small>ผู้รับงาน</small><p>${esc(state.users.find((x) => x.id === j.assignee)?.name || "ยังไม่มีช่างรับ")}${owner ? button("assign", "เปลี่ยน", "text-link") : ""}</p></div></div>${j.rush_requested ? '<span class="badge yellow">ลูกค้าขอด่วนตอนรับเครื่อง</span>' : ""}${"passcode" in j ? `<div class="note no-print">รหัสเครื่อง: <span id="device-code">••••••</span> ${button("reveal", "แสดง", "quiet")}</div>` : ""}<p class="muted">${esc(j.notes)}</p><div class="photos">${j.photos.map((p) => `<img src="${esc(p)}" alt="สภาพเครื่องที่รับเข้า">`).join("")}</div><div class="actions no-print">${front ? button("contact", "แก้ข้อมูลติดต่อ") + button("unlock", "ปลดล็อกหน้าเช็กสถานะ") : ""}</div></div><div class="panel"><h2>ใบเสนอราคา ${j.quotes.length ? "• " + j.quotes.length + " ฉบับ" : ""}</h2>${
      j.quotes.length
        ? [...j.quotes]
            .reverse()
            .map((q) => quoteHtml(q))
            .join("")
        : '<p class="muted">ช่างจะออกใบเสนอราคาหลังตรวจเครื่อง</p>'
    }${j.current_items ? '<div class="note">ราคาค่าบริการปัจจุบัน: ' + baht(j.current_items.reduce((s, i) => s + i.labor + i.parts, 0)) + "</div>" : ""}</div><div class="panel"><h2>ประวัติความคืบหน้า</h2>${timelineHtml(j.timeline)}</div></div><div><div class="panel"><h2>สรุปยอดรับเครื่องคืน</h2>${billHtml(j.receipt && !j.receipt.void ? j.receipt.bill : j.bill)}${j.needs_charges ? '<div class="note warning">รอเจ้าของร้านกำหนดยอดปิดงานก่อนรับเงิน</div>' : ""}${j.receipt ? `<div class="note">ใบเสร็จ ${esc(j.receipt.id)}<br>${dt(j.receipt.at)} • ${j.receipt.method === "cash" ? "เงินสด" : "โอน"}<br>ผู้รับ: ${esc(j.receipt.receiver)}<br>เงินทอน ${baht(j.receipt.change)}${j.receipt.void ? '<p class="error">ยกเลิก: ' + esc(j.receipt.void) + "</p>" : ""}</div><div class="actions no-print">${button("print-receipt", "พิมพ์ใบเสร็จ")}${owner && !j.receipt.void ? button("void-receipt", "ยกเลิกใบเสร็จ", "danger") : ""}</div>` : ""}<p class="footer-note">ค่าฝากเริ่มวันที่ 61 หลังแจ้งให้รับเครื่อง วันละ ฿20</p></div>${j.warranties?.length ? `<div class="panel"><h2>ประกันงานซ่อม</h2>${j.warranties.map((w, i) => `<div class="note"><strong>${esc(w.name)}</strong><br><small>${w.days} วัน • ${w.eligible ? "ยังอยู่ในประกัน เหลือ " + w.remaining + " วัน" : "พ้นประกัน / ไม่มีประกัน"}</small>${front && w.eligible ? button("warranty", "เปิดใบรับเคลม", "text-link", `data-item="${i}"`) : ""}</div>`).join("")}</div>` : ""}<div class="panel no-print"><h2>การแจ้งลูกค้า</h2>${notificationHtml(j)}</div></div></div>`
  );
}
function quoteHtml(q) {
  return `<div class="quote-item"><div class="row"><strong>ฉบับที่ ${q.version}</strong><span class="badge ${q.decision === "accepted" ? "green" : "yellow"}">${q.decision === "accepted" ? "ยืนยันแล้ว" : q.decision === "rejected" ? "ปฏิเสธแล้ว" : "รอยืนยัน"}</span></div><p><small>ส่ง ${dt(q.sent_at)} • ระยะเวลา ${q.days} วันทำการ</small></p>${q.items.map((i) => `<div class="bill-row"><span>${esc(i.name)}<br><small>ประกัน ${i.warranty} วัน • อะไหล่ ${baht(i.parts)}</small></span><strong>${baht(i.labor + i.parts)}</strong></div>`).join("")}<div class="bill-row"><strong>ยอดใบเสนอราคา</strong><strong>${baht(q.total)}</strong></div>${q.rush_eligible ? `<small>แบบด่วนเพิ่ม ${baht(rushFee(q.items.reduce((s, i) => s + i.labor, 0)))} • ภายใน 24 ชั่วโมงจากยืนยัน</small>` : `<small>แบบปกติ: ${esc(q.rush_reason)}</small>`}${q.data_loss ? '<div class="note warning">ข้อมูลในเครื่องอาจสูญหายจากการซ่อมรายการนี้</div>' : ""}${!q.notified_at ? '<p class="error">ยังไม่ได้โทรแจ้ง เริ่มนับ 7 วันหลังโทรแจ้งแล้ว</p>' : ""}</div>`;
}
function rushFee(labor) {
  return Math.ceil((labor * 1.5) / 10) * 10 - labor;
}
function notificationHtml(j) {
  return j.notifications.length
    ? [...j.notifications]
        .reverse()
        .map((n, rev) => {
          const i = j.notifications.length - 1 - rev;
          return `<div class="note"><span class="badge">${esc(n.channel)}</span> <small>${dt(n.at)}</small><p>${esc(n.text)}</p>${n.channel === "โทรศัพท์" ? (n.called ? '<span class="badge green">โทรแจ้งแล้ว</span>' : `<div class="actions">${button("called", "โทรแจ้งแล้ว", "", 'data-id="' + j.id + '" data-index="' + i + '" data-success="1"')}${button("called", "โทรไม่ติด", "quiet", 'data-id="' + j.id + '" data-index="' + i + '" data-success="0"')}</div>${n.attempted_at ? "<small>พยายามโทรล่าสุด " + dt(n.attempted_at) + "</small>" : ""}`) : "<small>ข้อความจำลอง • ยังไม่เชื่อม LINE จริง</small>"}</div>`;
        })
        .join("")
    : '<p class="muted">ยังไม่มีการแจ้ง</p>';
}
function calls() {
  const jobs = state.jobs.filter((j) =>
    j.notifications.some((n) => n.channel === "โทรศัพท์" && !n.called),
  );
  return (
    heading(
      "CUSTOMER CONTACT",
      "แจ้งลูกค้า",
      "ติดตามรายการต้องโทร และดูข้อความ LINE จำลอง",
    ) +
    `<div class="panel"><h2>รายการต้องโทรแจ้ง ${jobs.length} งาน</h2>${jobs.length ? jobs.map((j) => `<h3>${esc(j.id)} • ${esc(j.name)} • <a href="tel:${esc(j.phone)}">${esc(j.phone)}</a></h3>${notificationHtml(j)}`).join("") : '<div class="empty">ไม่มีรายการต้องโทรแจ้ง</div>'}</div><div class="panel"><h2>ข้อความจำลองล่าสุด</h2>${
      state.jobs
        .flatMap((j) =>
          j.notifications
            .filter((n) => n.channel !== "โทรศัพท์")
            .map((n) => ({ ...n, id: j.id })),
        )
        .sort((a, b) => b.at.localeCompare(a.at))
        .slice(0, 20)
        .map(
          (n) =>
            `<div class="note"><strong>${esc(n.id)}</strong> • <small>${dt(n.at)}</small><p>${esc(n.text)}</p></div>`,
        )
        .join("") || '<p class="muted">ยังไม่มีข้อความ</p>'
    }</div>`
  );
}
function reports() {
  const valid = state.jobs.filter((j) => j.receipt && !j.receipt.void),
    totals = {};
  valid.forEach((j) => {
    const d = j.receipt.at.slice(0, 10);
    totals[d] = (totals[d] || 0) + j.receipt.bill.total;
  });
  return (
    heading(
      "SHOP REPORTS",
      "รายงานร้าน",
      "จำนวนงานซ่อม งานเลยนัด และยอดรับเงินจริง",
    ) +
    `<div class="status-counts">${state.statuses.map((s) => `<div class="card"><small>${s}</small><div class="number">${state.jobs.filter((j) => j.status === s).length}</div></div>`).join("")}</div><br><div class="split"><div class="panel"><h2>ยอดรับเงินรายวัน</h2>${
      Object.entries(totals)
        .sort((a, b) => b[0].localeCompare(a[0]))
        .map(
          ([d, total]) =>
            `<div class="bill-row"><span>${day(d)}</span><strong>${baht(total)}</strong></div>`,
        )
        .join("") || '<div class="empty">ยังไม่มีรายรับ</div>'
    }</div><div class="panel"><h2>งานซ่อมเลยนัด ${state.jobs.filter((j) => j.urgency === "late").length} งาน</h2>${state.jobs
      .filter((j) => j.urgency === "late")
      .map(
        (j) =>
          `<div class="note">${esc(j.id)} • ${esc(j.model)} ${button("detail", "เปิด →", "text-link", `data-id="${j.id}"`)}</div>`,
      )
      .join("")}</div></div>`
  );
}
function settings() {
  return (
    heading(
      "SHOP SETTINGS",
      "ตั้งค่าร้าน",
      "ราคาใหม่ใช้กับใบเสนอราคาฉบับใหม่ ไม่กระทบฉบับที่ส่งแล้ว",
    ) +
    `<div class="panel"><h2>วันหยุดร้าน</h2><form id="holidays-form"><label>วันที่หยุด (หนึ่งวันต่อบรรทัด รูปแบบ YYYY-MM-DD)<textarea name="holidays" rows="4">${esc(state.holidays.join("\n"))}</textarea></label><div class="actions"><button class="primary" type="submit">บันทึกวันหยุด</button></div></form></div><div class="panel"><h2>ตารางค่าตรวจและรายการซ่อม</h2><form id="pricing-form"><div class="form-grid">${Object.entries(
      state.devices,
    )
      .map(([id, n]) =>
        field(
          "inspection_" + id,
          n,
          "number",
          state.inspection[id],
          'min="0" step="1" required',
        ),
      )
      .join(
        "",
      )}</div><div class="table-wrap"><table><thead><tr><th>รายการ</th><th>ค่าแรง</th><th>วันทำการ</th><th>ประกัน</th></tr></thead><tbody>${state.catalog.map((i) => `<tr><td>${i.code} ${esc(i.name)}</td><td><input type="number" name="labor_${i.code}" value="${i.labor}" min="0" required aria-label="ค่าแรง ${i.code}"></td><td><input type="number" name="days_${i.code}" value="${i.days}" min="1" max="365" required aria-label="วันทำการ ${i.code}"></td><td><select name="warranty_${i.code}" aria-label="ประกัน ${i.code}">${[0, 30, 90].map((w) => `<option ${w === i.warranty ? "selected" : ""}>${w}</option>`).join("")}</select></td></tr>`).join("")}</tbody></table></div><div class="actions"><button class="primary" type="submit">บันทึกตารางราคา</button></div></form></div><div class="panel"><div class="panel-title"><h2>บัญชีพนักงาน</h2>${button("user-new", "＋ เปิดบัญชี")}</div>${state.users.map((u) => `<div class="bill-row"><div>${esc(u.name)} <small>${esc(u.id)}@somdee.test • ${u.active ? "เปิดใช้งาน" : "ปิดแล้ว"}</small></div>${button("user-edit", "จัดการ", "", 'data-id="' + u.id + '"')}</div>`).join("")}</div>${state.test_mode ? `<div class="panel"><h2>เครื่องมือทดสอบ</h2><div class="note warning">รีเซ็ตจะลบงานซ่อมทั้งหมด ใช้กับฐานข้อมูลทดสอบเท่านั้น</div><form id="test-form">${field("now", "เวลาทดสอบ (เวลาไทย)", "datetime-local", state.now.slice(0, 16), "required")}<div class="actions"><button class="primary" type="submit">ตั้งเวลาทดสอบ</button>${button("test-reset", "รีเซ็ตตัวอย่าง 9 งาน", "danger")}</div></form></div>` : ""}`
  );
}
function quoteModal(adjust = false) {
  const j = current();
  modal(
    adjust ? "ปรับราคาค่าบริการ" : "สร้างใบเสนอราคาฉบับใหม่",
    `<form id="quote-form" data-adjust="${adjust}"><div class="note">${adjust ? "เพิ่มไม่เกิน 10% จากฉบับล่าสุดที่ยืนยัน ทำต่อได้ • เกินกว่านั้นให้ส่งใบเสนอราคาฉบับใหม่" : "ใบเสนอราคาที่ส่งแล้วจะถูกล็อก ลูกค้าต้องยืนยันก่อนซ่อม"}</div><div id="quote-items"></div>${button("add-item", "＋ เพิ่มรายการ", "text-link", 'type="button"')}<div class="form-grid">${field("days", "ระยะเวลา (วันทำการ)", "number", 1, 'min="1" max="365" required')}${check("order_parts", "ต้องสั่งอะไหล่")}${check("cannot_24h", "ทำไม่ทัน 24 ชั่วโมง")}${check("data_loss", "ข้อมูลในเครื่องอาจสูญหาย")}</div><div class="note" id="quote-total">ยอดใบเสนอราคา ฿0</div><div class="actions"><button type="submit" class="primary">${adjust ? "บันทึกการปรับราคา" : "ส่งใบเสนอราคา"}</button></div></form>`,
  );
  const items = adjust ? j.current_items || [] : [];
  if (items.length) items.forEach((i) => addItem(i));
  else addItem();
}
function addItem(item) {
  const j = current(),
    catalog = state.catalog.filter((i) => i.types.includes(j.device)),
    el = document.createElement("div");
  el.className = "quote-item";
  el.innerHTML = `<div class="form-grid"><label>รายการซ่อม<select class="item-code" aria-label="รายการซ่อม">${catalog.map((i) => `<option value="${i.code}" ${item?.code === i.code ? "selected" : ""}>${i.code} ${esc(i.name)}</option>`).join("")}<option value="CUSTOM" ${item?.code === "CUSTOM" ? "selected" : ""}>รายการนอกตาราง</option></select></label><label>ค่าแรง<input class="item-labor" type="number" min="0" step="1" required value="${item?.labor ?? catalog[0]?.labor ?? 0}"></label><label>ค่าอะไหล่<input class="item-parts" type="number" min="0" step="1" required value="${item?.parts ?? 0}"></label><label>ชื่อรายการนอกตาราง<input class="item-name" value="${esc(item?.code === "CUSTOM" ? item.name : "")}" maxlength="200"></label><label>ประกันรายการนอกตาราง<select class="item-warranty" aria-label="ประกันรายการนอกตาราง">${[0, 30, 90].map((w) => `<option ${w === (item?.warranty ?? 90) ? "selected" : ""}>${w}</option>`).join("")}</select></label>${button("remove-item", "ลบรายการ", "danger", 'type="button"')}</div>`;
  $("#quote-items").append(el);
  updateQuoteTotal();
}
function readItems() {
  return [...document.querySelectorAll("#quote-items>.quote-item")].map(
    (el) => ({
      code: el.querySelector(".item-code").value,
      labor: Number(el.querySelector(".item-labor").value),
      parts: Number(el.querySelector(".item-parts").value),
      name: el.querySelector(".item-name").value,
      warranty: Number(el.querySelector(".item-warranty").value),
    }),
  );
}
function updateQuoteTotal() {
  if ($("#quote-total"))
    $("#quote-total").textContent =
      "ยอดใบเสนอราคา " +
      baht(readItems().reduce((s, i) => s + i.labor + i.parts, 0));
}
function current() {
  return state.jobs.find((j) => j.id === selected);
}
async function act(data, id = selected) {
  await api("/api/jobs/" + id, data);
  closeModal();
  await refresh();
  toast("บันทึกเรียบร้อย");
}
function checkoutModal() {
  const j = current();
  modal(
    "รับเงินและคืนเครื่อง",
    `<form id="checkout-form">${billHtml(j.bill)}${state.jobs.some((x) => x.id !== j.id && x.phone === j.phone && state.statuses.slice(5, 8).includes(x.status)) ? button("batch-checkout", "รับหลายเครื่องและรวมใบเสร็จ", "text-link") : ""}${j.needs_charges ? '<div class="note warning">เจ้าของร้านต้องกำหนดยอดก่อนคืนเครื่อง</div>' : ""}<br><div class="form-grid">${field("receiver", "ชื่อผู้รับเครื่อง *", "text", j.name, "required")}${field("last4", "เบอร์ลูกค้า 4 ตัวท้าย *", "text", "", 'required pattern="[0-9]{4}" maxlength="4" inputmode="numeric"')}<label>วิธีชำระ<select name="method"><option value="cash">เงินสด</option><option value="transfer">โอน</option></select></label>${field("paid", "รับเงิน (บาท) *", "number", j.bill.total, 'required min="0" step="1"')}${field("company", "ชื่อบริษัท (ถ้ามี)")}${field("tax_id", "เลขผู้เสียภาษี 13 หลัก", "text", "", 'pattern="[0-9]{13}" maxlength="13"')}</div><div class="actions"><button class="primary" type="submit">รับเงินครบและคืนเครื่อง</button></div></form>`,
  );
}
function batchCheckoutModal() {
  const j = current(),
    jobs = state.jobs.filter(
      (x) =>
        x.phone === j.phone && state.statuses.slice(5, 8).includes(x.status),
    );
  modal(
    "รับหลายเครื่องและรวมใบเสร็จ",
    `<form id="batch-form"><div class="note">เลือกเครื่องที่ลูกค้าคนเดียวกันรับและจ่ายพร้อมกันวันนี้</div>${jobs.map((x) => `<label class="check"><input type="checkbox" name="batch-id" value="${x.id}" ${x.id === j.id ? "checked" : ""}>${x.id} • ${esc(x.model)} • ${baht(x.bill.total)}</label>`).join("<br>")}<br><div class="form-grid">${field("receiver", "ชื่อผู้รับเครื่อง", "text", j.name, "required")}${field("last4", "เบอร์ 4 ตัวท้าย", "text", "", 'required pattern="[0-9]{4}"')}${field("paid", "ยอดรับเงินรวม", "number", j.bill.total, 'required min="0"')}<label>วิธีจ่าย<select name="method"><option value="cash">เงินสด</option><option value="transfer">โอน</option></select></label>${field("company", "ชื่อบริษัท")}${field("tax_id", "เลขผู้เสียภาษี", "text", "", 'pattern="[0-9]{13}"')}</div><div class="actions"><button class="primary" type="submit">รับเงินและคืนเครื่องที่เลือก</button></div></form>`,
  );
}
function chargesModal() {
  const j = current(),
    c = j.manual_charges || { inspection: 0, labor: 0, parts: 0 };
  modal(
    "ปรับยอดและส่วนลด",
    `<form id="charges-form">${j.needs_charges || j.manual_charges ? `<div class="note">กรอกยอดปิดงานแยก 3 ช่อง ไม่หักค่าตรวจซ้ำ</div><div class="form-grid">${field("inspection", "ค่าตรวจ", "number", c.inspection, 'required min="0"')}${field("labor", "ค่าแรงที่ทำจริง", "number", c.labor, 'required min="0"')}${field("parts", "ค่าอะไหล่ที่ลูกค้าเก็บไว้", "number", c.parts, 'required min="0"')}</div>` : ""}<br>${field("discount", "ส่วนลด (บาท)", "number", j.discount || 0, 'required min="0"')}<br>${check("waive", "ยกเว้นค่าตรวจเช็ก")}${check("restore_rush", "เก็บค่าบริการด่วนกลับ (กรณีเสร็จเลยกำหนด)")}${check("warranty_override", "ให้ประกันตามรายการ แม้งานซ่อมไม่สำเร็จหรือยกเลิก", !!j.warranty_override)}<br>${field("reason", "เหตุผล *", "text", "", "required")}<div class="actions"><button class="primary" type="submit">บันทึกยอด</button></div></form>`,
  );
}
function renderTrack() {
  root.innerHTML = `<div class="track-page"><div class="track-header">${brand()}<a href="/">สำหรับพนักงาน →</a></div><div class="panel"><div class="eyebrow">REPAIR TRACKING</div><h1>เครื่องของคุณถึงไหนแล้ว?</h1><p class="muted">ดูความคืบหน้าและยืนยันใบเสนอราคาได้ที่นี่</p><form id="track-form"><div class="form-grid">${field("id", "เลขใบรับ", "text", trackCredentials?.id || new URLSearchParams(location.search).get("id") || "", 'required placeholder="SD-261106-001" autocomplete="off"')}${field("last4", "เบอร์โทร 4 ตัวท้าย", "text", trackCredentials?.last4 || "", 'required pattern="[0-9]{4}" maxlength="4" inputmode="numeric" autocomplete="off"')}</div><div class="actions"><button class="primary" type="submit">เช็กสถานะ →</button></div><div id="track-error" class="error" role="alert"></div></form></div>${trackResult ? trackDetails() : ""}<p class="footer-note">ซ่อมดี IT Service • จันทร์–เสาร์ 10:00–19:00<br>เก็บเลขใบรับและเบอร์โทรไว้สำหรับรับเครื่องคืน</p></div>`;
}
function trackDetails() {
  const j = trackResult,
    q = j.quotes?.at(-1);
  return `<div class="panel"><small>${esc(j.id)} • ${esc(j.name)}</small><h2>${esc(j.model)}</h2><div class="note">${esc(j.status)}</div><p>วันนัดรับ: ${day(j.pickup)}${j.rush ? "<br>กำหนดคืนด่วน: " + dt(j.deadline) : ""}</p>${q ? quoteHtml(q) : ""}${j.status === "รอลูกค้ายืนยันราคา" && q && !q.decision ? `<div class="note">กรุณาตอบภายใน 7 วันนับจากวันที่แจ้งราคา<br>ค่าตรวจเช็กจะหักจากยอดค่าบริการเมื่อยืนยันซ่อม</div><div class="actions">${button("track-accept", "ยืนยันแบบปกติ", "primary")}${q.rush_eligible ? button("track-rush", "ยืนยันแบบด่วน", "primary") : ""}${button("track-reject", "ไม่ซ่อม", "danger")}</div>` : ""}</div><div class="panel"><h2>สรุปค่าบริการ</h2>${billHtml(j.bill)}</div><div class="panel"><h2>ความคืบหน้า</h2>${timelineHtml(j.timeline)}</div>`;
}
function printDocument(receipt = false, label = false) {
  const j = current();
  if (receipt && !j.receipt) return;
  const content = label
    ? `<h1>${esc(j.id)}</h1><p>${esc(j.model)}</p>`
    : receipt
      ? `${brand()}<h1>ใบเสร็จรับเงิน</h1><p>${esc(j.receipt.id)} • ${dt(j.receipt.at)}</p><p>ใบรับ ${esc(j.id)}<br>ลูกค้า ${esc(j.name)}<br>บริษัท ${esc(j.receipt.company)} ${esc(j.receipt.tax_id)}</p>${j.receipt.combined ? j.receipt.combined.map((x) => `<h3>${esc(x.id)} • ${esc(x.model)}</h3>${billHtml(x.bill)}`).join("") : billHtml(j.receipt.bill)}<p>รับเงิน ${baht(j.receipt.combined_paid ?? j.receipt.paid)} • ทอน ${baht(j.receipt.combined_change ?? j.receipt.change)}<br>ผู้รับเครื่อง ${esc(j.receipt.receiver)}</p>${j.receipt.void ? "<h2>ยกเลิกใบเสร็จ: " + esc(j.receipt.void) + "</h2>" : ""}<small>ใบเสร็จรับเงิน ไม่ใช่ใบกำกับภาษี</small>`
      : `${brand()}<h1>ใบรับ • ${esc(j.id)}</h1><p>${dt(j.created_at)}</p><p>ลูกค้า: ${esc(j.name)} • ${esc(j.phone)}<br>เครื่อง: ${esc(j.model)}<br>Serial: ${esc(j.serial)}<br>อาการ: ${esc(j.symptom)}<br>อุปกรณ์: ${esc(j.accessories)}</p><div class="note">ลูกค้ายอมรับความเสี่ยงเรื่องข้อมูลแล้ว<br>ค่าตรวจเช็ก ${baht(j.inspection_fee)} เก็บตอนรับเครื่องคืน</div><p>เช็กสถานะ: ${esc(location.origin + "/track?id=" + j.id)}<br>ใช้เบอร์โทร 4 ตัวท้ายเพื่อดูข้อมูล</p><div id="receipt-qr"></div><p>ลงชื่อผู้ส่งเครื่อง __________________</p>`;
  const original = root.innerHTML;
  root.innerHTML = `<div class="receipt">${content}</div>`;
  if (!receipt && !label) {
    const qr = qrcode(0, "M");
    qr.addData(location.origin + "/track?id=" + j.id);
    qr.make();
    $("#receipt-qr").innerHTML = qr.createSvgTag({
      cellSize: 3,
      margin: 2,
      scalable: true,
    });
  }
  window.print();
  root.innerHTML = original;
}
root.addEventListener("input", (e) => {
  if (e.target.id === "job-search") {
    query = e.target.value;
    $("#job-table").innerHTML = table(filteredJobs());
  }
});
document.addEventListener("change", async (e) => {
  if (e.target.id === "status-filter") {
    filter = e.target.value;
    $("#job-table").innerHTML = table(filteredJobs());
  }
  if (e.target.classList.contains("item-code")) {
    const el = e.target.closest(".quote-item"),
      item = state.catalog.find((i) => i.code === e.target.value);
    if (item) {
      el.querySelector(".item-labor").value = item.labor;
      $("#quote-form [name=days]").value = item.days;
    }
    updateQuoteTotal();
  }
  if (e.target.id === "photo-files") {
    const files = [...e.target.files];
    $("#photo-preview").innerHTML = "";
    for (const f of files) {
      if (f.size > 2 * 1024 * 1024) {
        toast("รูปต้องมีขนาดไม่เกิน 2 MB");
        e.target.value = "";
        return;
      }
      const img = document.createElement("img");
      img.src = URL.createObjectURL(f);
      img.alt = "รูปสภาพเครื่อง";
      img.onload = () => URL.revokeObjectURL(img.src);
      $("#photo-preview").append(img);
    }
  }
});
document.addEventListener("input", (e) => {
  if (e.target.closest("#quote-items")) updateQuoteTotal();
});
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-action]");
  if (!b) return;
  const a = b.dataset.action;
  e.preventDefault();
  try {
    if (a === "nav") {
      page = b.dataset.page;
      selected = null;
      render();
    } else if (a === "detail") {
      selected = b.dataset.id;
      page = "detail";
      render();
    } else if (a === "logout") {
      await api("/api/logout", {});
      state = null;
      renderLogin();
    } else if (a === "close") closeModal();
    else if (a === "quote" || a === "adjust") quoteModal(a === "adjust");
    else if (a === "add-item") addItem();
    else if (a === "remove-item") {
      b.closest(".quote-item").remove();
      updateQuoteTotal();
    } else if (a === "reveal")
      $("#device-code").textContent = current().passcode || "ไม่ได้ให้รหัส";
    else if (a === "checkout") checkoutModal();
    else if (a === "charges") chargesModal();
    else if (a === "batch-checkout") batchCheckoutModal();
    else if (
      a === "print-intake" ||
      a === "print-receipt" ||
      a === "print-label"
    )
      printDocument(a === "print-receipt", a === "print-label");
    else if (a === "claim") {
      if (state.user.role === "owner") assignmentModal("claim");
      else await act({ action: "claim" });
    } else if (a === "assign") assignmentModal("assign");
    else if (a === "unlock") {
      await api("/api/unlock", { id: selected });
      toast("ปลดล็อกแล้ว");
    } else if (a === "called")
      await act(
        {
          action: "called",
          index: Number(b.dataset.index),
          success: b.dataset.success === "1",
        },
        b.dataset.id,
      );
    else if (a === "status") {
      const target = Number(b.dataset.target);
      if (target === 4)
        modal(
          "รออะไหล่และเปลี่ยนวันนัด",
          `<form id="parts-form">${field("pickup", "วันนัดใหม่ *", "date", "", "required")}<div class="actions"><button class="primary" type="submit">แจ้งลูกค้าและบันทึก</button></div></form>`,
        );
      else await act({ action: "status", status: state.statuses[target] });
    } else if (a === "deny-claim") {
      modal(
        "ยืนยันว่าเคลมไม่ได้",
        `<form id="claim-deny-form">${field("reason", "เหตุผล *", "text", "", "required")}<p class="muted">งานซ่อมจะคิดราคาปกติหลังยืนยันเหตุผลนี้</p><button class="danger" type="submit">ยืนยันเคลมไม่ได้</button></form>`,
      );
    } else if (a === "cancel" || a === "void-receipt") {
      modal(
        a === "cancel" ? "ยกเลิกงานซ่อม" : "ยกเลิกใบเสร็จ",
        `<form id="reason-form" data-kind="${a}">${field("reason", "เหตุผล *", "text", "", "required")}<div class="actions"><button class="danger" type="submit">ยืนยันการยกเลิก</button></div></form>`,
      );
    } else if (a === "reopen") await act({ action: "reopen" });
    else if (a === "contact") {
      const j = current();
      modal(
        "แก้ข้อมูลติดต่อ",
        `<form id="contact-form"><div class="stack">${field("name", "ชื่อ", "text", j.name, "required")}${field("phone", "เบอร์โทร", "tel", j.phone, "required")}${field("line", "LINE", "text", j.line)}</div><div class="actions"><button class="primary" type="submit">บันทึกพร้อมประวัติเดิม</button></div></form>`,
      );
    } else if (a === "phone-response") {
      modal(
        "บันทึกคำตอบลูกค้าทางโทรศัพท์",
        `<form id="phone-form"><label>คำตอบ<select name="decision"><option value="accept">ยืนยันแบบปกติ</option>${current().quotes.at(-1).rush_eligible ? '<option value="rush">ยืนยันแบบด่วน</option>' : ""}<option value="reject">ไม่ซ่อม</option></select></label><div class="actions"><button type="submit" class="primary">บันทึกคำตอบ</button></div></form>`,
      );
    } else if (a === "warranty") {
      const j = current();
      root.querySelector(".content").innerHTML = intake({
        ...j,
        item: Number(b.dataset.item),
      });
      window.scrollTo(0, 0);
    } else if (a === "user-edit" || a === "user-new") userModal(b.dataset.id);
    else if (a === "test-reset") {
      modal(
        "รีเซ็ตฐานข้อมูลทดสอบ",
        `<p>จะลบงานซ่อมทั้งหมด แล้วสร้าง SD-TEST-001 ถึง 009 ใหม่</p><form id="reset-form"><button class="danger" type="submit">ยืนยันรีเซ็ตข้อมูลทดสอบ</button></form>`,
      );
    } else if (a.startsWith("track-")) {
      const accept = a !== "track-reject",
        rush = a === "track-rush";
      modal(
        accept ? "ยืนยันใบเสนอราคา" : "ยืนยันไม่ซ่อม",
        `<form id="track-response" data-accept="${accept}" data-rush="${rush}"><p>${accept ? (rush ? "ยืนยันซ่อมแบบด่วน มีค่าบริการด่วนตามใบเสนอราคา" : "ยืนยันซ่อมแบบปกติ") : "ไม่ซ่อม และชำระค่าตรวจตามเงื่อนไขร้าน"}</p><button class="${accept ? "primary" : "danger"}" type="submit">ยืนยันคำตอบ</button></form>`,
      );
    }
  } catch (err) {
    toast(err.message);
  }
});
function assignmentModal(action) {
  modal(
    "เลือกช่างผู้รับงาน",
    `<form id="assign-form" data-kind="${action}"><label>ช่าง<select name="assignee">${state.users
      .filter((u) => u.role === "tech" && u.active)
      .map((u) => `<option value="${u.id}">${esc(u.name)}</option>`)
      .join(
        "",
      )}</select></label><p class="muted">เจ้าของร้านมอบงานนอกตารางทักษะได้เมื่อช่างลา</p><button type="submit" class="primary">มอบงานซ่อม</button></form>`,
  );
}
function userModal(id) {
  const u = state.users.find((u) => u.id === id);
  modal(
    u ? "จัดการบัญชี" : "เปิดบัญชีพนักงาน",
    `<form id="user-form"><div class="stack">${field("id", "รหัสบัญชี (ก่อน @somdee.test)", "text", u?.id || "", `required pattern="[a-z][a-z0-9]{1,30}" ${u ? "readonly" : ""}`)}${field("name", "ชื่อ", "text", u?.name || "", "required")}<label>ตำแหน่ง<select name="role" ${u ? "disabled" : ""}>${[
      ["owner", "เจ้าของร้าน"],
      ["front", "หน้าร้าน"],
      ["tech", "ช่าง (boy / bank / em)"],
    ]
      .map(
        ([r, n]) =>
          `<option value="${r}" ${u?.role === r ? "selected" : ""}>${n}</option>`,
      )
      .join(
        "",
      )}</select></label>${field("password", "รหัสผ่านใหม่ (10 ตัวอักษรขึ้นไป)", "password", "", 'minlength="10" autocomplete="new-password" ' + (u ? "" : "required"))}${check("active", "เปิดใช้งานบัญชี", u ? !!u.active : true)}</div><div class="actions"><button class="primary" type="submit">บันทึกบัญชี</button></div></form>`,
  );
}
async function readPhoto(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}
document.addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target,
    d = formData(f),
    submit = f.querySelector("[type=submit]");
  if (submit) submit.disabled = true;
  try {
    if (f.getAttribute("id") === "login-form") {
      await api("/api/login", d);
      page = "dashboard";
      await refresh();
    } else if (f.getAttribute("id") === "intake-form") {
      d.photos = await Promise.all([...$("#photo-files").files].map(readPhoto));
      let j;
      if (f.dataset.claim)
        j = await api("/api/claim", {
          id: f.dataset.claim,
          item: Number(f.dataset.item),
          intake: d,
        });
      else j = await api("/api/jobs", d);
      selected = j.id;
      page = "detail";
      await refresh();
      toast("เปิดใบรับ " + j.id + " แล้ว");
    } else if (f.getAttribute("id") === "quote-form") {
      await act({
        action: f.dataset.adjust === "true" ? "adjust" : "quote",
        items: readItems(),
        days: Number(d.days),
        order_parts: d.order_parts,
        cannot_24h: d.cannot_24h,
        data_loss: d.data_loss,
      });
    } else if (f.getAttribute("id") === "assign-form")
      await act({ action: f.dataset.kind, assignee: d.assignee });
    else if (f.getAttribute("id") === "parts-form")
      await act({
        action: "status",
        status: state.statuses[4],
        pickup: d.pickup,
      });
    else if (f.getAttribute("id") === "reason-form")
      await act({
        action: f.dataset.kind === "cancel" ? "cancel" : "void_receipt",
        reason: d.reason,
      });
    else if (f.getAttribute("id") === "phone-form")
      await act({
        action: "respond",
        accept: d.decision !== "reject",
        rush: d.decision === "rush",
      });
    else if (f.getAttribute("id") === "contact-form")
      await act({ action: "contact", ...d });
    else if (f.getAttribute("id") === "charges-form") {
      const data = {
        action: "charges",
        discount: Number(d.discount),
        reason: d.reason,
        waive: d.waive,
        restore_rush: d.restore_rush,
        warranty_override: d.warranty_override,
      };
      if ("inspection" in d)
        data.manual_charges = {
          inspection: Number(d.inspection),
          labor: Number(d.labor),
          parts: Number(d.parts),
        };
      await act(data);
    } else if (f.getAttribute("id") === "claim-deny-form") {
      await api("/api/claim-deny", { id: selected, reason: d.reason });
      closeModal();
      await refresh();
      toast("บันทึกเหตุผลแล้ว");
    } else if (f.getAttribute("id") === "batch-form") {
      const ids = [...f.querySelectorAll("[name=batch-id]:checked")].map(
        (x) => x.value,
      );
      await api("/api/checkout", {
        ids,
        receiver: d.receiver,
        last4: d.last4,
        method: d.method,
        paid: Number(d.paid),
        company: d.company,
        tax_id: d.tax_id,
      });
      closeModal();
      await refresh();
      toast("รับเงินและคืนเครื่องทุกใบที่เลือกแล้ว");
    } else if (f.getAttribute("id") === "checkout-form")
      await act({ action: "checkout", ...d, paid: Number(d.paid) });
    else if (f.getAttribute("id") === "holidays-form") {
      await api("/api/settings", {
        holidays: d.holidays
          .split("\n")
          .map((x) => x.trim())
          .filter(Boolean),
      });
      await refresh();
      toast("บันทึกวันหยุดแล้ว");
    } else if (f.getAttribute("id") === "pricing-form") {
      const inspection = Object.fromEntries(
          Object.keys(state.devices).map((id) => [
            id,
            Number(d["inspection_" + id]),
          ]),
        ),
        catalog = state.catalog.map((i) => ({
          ...i,
          labor: Number(d["labor_" + i.code]),
          days: Number(d["days_" + i.code]),
          warranty: Number(d["warranty_" + i.code]),
        }));
      await api("/api/settings", {
        holidays: state.holidays,
        inspection,
        catalog,
      });
      await refresh();
      toast("บันทึกราคาแล้ว");
    } else if (f.getAttribute("id") === "user-form") {
      await api("/api/users", d);
      closeModal();
      await refresh();
      toast("บันทึกบัญชีแล้ว");
    } else if (f.getAttribute("id") === "test-form") {
      await api("/api/test", { now: d.now });
      await refresh();
      toast("ตั้งเวลาทดสอบแล้ว");
    } else if (f.getAttribute("id") === "reset-form") {
      await api("/api/test", { reset: true });
      closeModal();
      await refresh();
      toast("สร้างข้อมูลตัวอย่าง 9 งานแล้ว");
    } else if (f.getAttribute("id") === "track-form") {
      trackResult = null;
      trackCredentials = { id: d.id.trim().toUpperCase(), last4: d.last4 };
      trackResult = await api("/api/track", trackCredentials);
      renderTrack();
    } else if (f.getAttribute("id") === "track-response") {
      trackResult = await api("/api/track", {
        ...trackCredentials,
        accept: f.dataset.accept === "true",
        rush: f.dataset.rush === "true",
      });
      closeModal();
      renderTrack();
      toast("บันทึกคำตอบแล้ว");
    }
  } catch (err) {
    const error = $("#modal").open
      ? $("#modal-error")
      : f.querySelector(".error");
    if (error) error.textContent = err.message;
    else toast(err.message);
  } finally {
    if (submit) submit.disabled = false;
  }
});
if (location.pathname === "/track") renderTrack();
else refresh().catch(() => renderLogin());
