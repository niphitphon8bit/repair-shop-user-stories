# Implementation

Implemented from `REQUIREMENTS.md`, the answers in §7 of `OWNER-ANSWERS.md`, and both ADRs. Existing interview, owner answers, stories, glossary, and requirements remain unchanged.

## Structure

| File | Responsibility |
|---|---|
| `app/domain.py` | Money, inspection credit, rush rounding, calendar, storage, catalog and quote validation |
| `app/server.py` | HTTP API, sessions, permissions, SQLite transactions, shop workflows, background maintenance |
| `app/demo.py` | Isolated persistent demo with the nine documented scenarios |
| `static/app.js` | Thai staff workspace, customer tracking, forms, printing and local QR generation |
| `static/style.css` | Responsive layout and print styles; bundled Thai fonts work offline |
| `tests/test_domain.py` | Deterministic business boundaries |
| `tests/test_api.py` | HTTP workflows, authorization, concurrency, lockout, expiry, warranty and billing |
| `tests/browser/shop.spec.js` | Browser workflows, mobile layout, prints and secret isolation |

## Requirement mapping

| Requirements | Implementation / entry point |
|---|---|
| FR-01–13, 81, 88 | Intake form, `new_job`, staff-specific serializer, checkout passcode removal, maintenance retention |
| FR-14–22, 83, 89, 91–92 | Login, users, role checks, `claim`, `assign`, transition graph, catalog snapshots |
| FR-23–33, 72–74, 78, 82, 85–86, 90 | `quote`, `respond`, `adjust`, `reopen`, customer tracking and zero-price warranty flow |
| FR-34–47, 75–77, 84, 87, 94 | `payable`, business calendars, rush deadline, manual charges, notifications, daily reminders |
| FR-48–56, 79 | Simulated LINE outbox, telephone tasks, server-side lookup gate and receipt-wide lockout |
| FR-57–70, 80, 93 | Item warranty, referenced claim, individual / combined checkout, invoice void, report and discount |
| FR-71 | Closing reason stored separately from the nine immutable customer status labels, per ADR-0002 |
| NFR-01–14 | Responsive layouts, no customer account, filtered server responses, atomic sequence and claim operations, deterministic tests and test-mode clock |

Each job owns its contact fields, as required by ADR-0001. Searching a phone number does not create a customer record or expose all same-phone jobs to a customer. A combined invoice requires the operator to select devices being paid for and collected together.

## Persistence and security

All state lives in SQLite: jobs with versioned quotation snapshots, users with salted PBKDF2 hashes, hashed session tokens with an eight-hour expiry, daily sequences, settings and rate-limit attempts. Mutation transactions finish before successful HTTP responses. A process lock plus SQLite write transactions serialize competing claims and daily numbers. Run one application process for this deployment.

Device passcodes are removed from unauthorized API responses and deleted from the live job at handover. Receipt rendering constructs a clean document instead of printing the staff page. No customer credentials go in URL parameters; QR includes only receipt ID. Customer data is sent in JSON POST bodies. Session cookies are HttpOnly and SameSite Strict; POST requests enforce same-origin when Origin is present. Static content uses CSP and does not rely on remote scripts, fonts or analytics.

The SQLite file is permission 0600; device passcodes are not encrypted separately inside that file. Restrict database/backups to authorized operators. Deletion from live records does not purge older backups. The bundled server is intended for local use; internet deployment requires HTTPS and an appropriate reverse proxy.

## Time and notifications

Calendar rules use Bangkok time; the day of an event is day zero. Quotations expire on day eight. Phone-only jobs start their clock when the particular quotation notification is marked called successfully. Failed calls and calls about older statuses do not start that clock. Tracking locks unlock at exactly fifteen minutes.

Normal pickup dates skip Sundays, configured holidays, and Mondays for printers. Rush deadlines preserve 19:00 exactly; later closing times roll forward to the next opening. Late completion removes the rush fee unless the owner explicitly restores it. Storage is charged only after the readiness notification, for every applicable return state, starting on day 61.

A background tick every 30 seconds and request-time maintenance perform expiration, daily reminder generation and photo retention. The process must be running for timely notifications; restarting catches up at the next maintenance pass. LINE is a local outbox, matching the specified simulation scope; telephone completion remains a human action.

## Test tools

Test endpoints require both `SHOP_TEST_MODE=1` and an owner session. Fixed time is ignored when test mode is disabled. Demo reset replaces jobs and sequences, preserving employee accounts and configured prices/holidays. Test seed jobs intentionally omit photo fixtures and some old historical receipt details; actual intake enforces the required photos.

Core acceptance examples are reproduced: `SD-TEST-001` ฿1,290; `002` ฿3,650; `007` ฿100; warranty day 90 valid and day 31 invalid for the corresponding items.
