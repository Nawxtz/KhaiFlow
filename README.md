# KhaiFlow — LINE Commerce Bot

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-14_App_Router-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![LINE Bot SDK](https://img.shields.io/badge/LINE_Bot_SDK-v3-00C300?logo=line&logoColor=white)](https://developers.line.biz/)
[![PDPA Compliant](https://img.shields.io/badge/PDPA-Compliant-success)](#pdpa-privacy--data-retention)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> KhaiFlow is a production-grade conversational e-commerce engine for LINE Official Accounts that transforms unstructured Thai delivery addresses into validated orders with atomic stock reservations, HMAC-signed PromptPay QR payments, and bilingual seller operations.

<!-- add demo screenshot here -->

---

## What It Does

The **KhaiFlow LINE Commerce Bot** automates social commerce for Thai retail merchants on LINE. Buyers effortlessly browse product catalogs via rich Flex carousels, configure items with a guided tap-to-order flow or conversational free-text requests, and provide unstructured Thai delivery addresses that are parsed and validated fully offline without external data leakage. Once confirmed, the system issues dynamically signed PromptPay QR codes with strict reservation timeouts and automated verification, before pushing fulfilled orders directly to Google Sheets and dispatching buyer notifications. Merchants supervise inventory, review high-risk payments, and manage catalog conflicts in real time through an internationalized (EN/TH) Next.js Seller Portal.

---

## Architecture

```mermaid
graph TD
  Buyer[LINE Buyer] --> Webhook[FastAPI Webhook]
  Webhook --> IntentRouter[Intent Router]
  IntentRouter --> OrderService[Order Service]
  IntentRouter --> AddressEngine[ThaiSmartAddress Engine]
  IntentRouter --> Cascade[Free-text Cascade]
  Cascade --> RulesEngine[Rules Engine]
  Cascade --> Embeddings[Embeddings Search]
  Cascade --> LLM[LLM Router - OpenRouter]
  OrderService --> DB[(PostgreSQL)]
  OrderService --> Sheets[Google Sheets]
  OrderService --> QRService[QR + HMAC]
  Webhook --> GatewayWebhook[Gateway Webhook]
  GatewayWebhook --> ReservationService[Reservation Service]
  Seller[Seller Portal - Next.js] --> FastAPI[FastAPI REST]
  FastAPI --> DB
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Bot backend** | FastAPI, Python 3.12, SQLAlchemy, Alembic |
| **Database** | PostgreSQL 16 |
| **LINE integration** | LINE Bot SDK v3 |
| **Address parsing** | ThaiSmartAddress (local/offline) |
| **Free-text search** | RapidFuzz + TF-IDF + OpenRouter LLM |
| **Payment QR** | PromptPay EMVCo + HMAC-SHA256 |
| **Seller portal** | Next.js 14 App Router, TypeScript, Tailwind CSS |
| **i18n** | EN / TH (100% key parity across bot and portal) |
| **Tests** | pytest (124 backend) + Vitest (14 portal) |

---

## Key Engineering Highlights

- **Atomic Stock Reservation:** Uses atomic conditional `UPDATE inventory SET reserved=reserved+:qty WHERE (stock-reserved) >= :qty` to guarantee zero overselling under high concurrency without fragile SELECT-then-UPDATE race conditions.
- **PostgreSQL Concurrency Proof:** Verified with `threading.Barrier(2)` concurrent race tests executing against real PostgreSQL instances, proving exactly-one-wins stock reservation.
- **HMAC-SHA256 Signed Payment QR:** Dynamic PromptPay EMVCo payload generation signed with HMAC-SHA256; validated via `hmac.compare_digest` to prevent parameter tampering and timing attacks.
- **Zero-Query Webhook Security:** Enforces strict LINE signature verification at the webhook entry point; proven via SQLAlchemy event listeners to execute zero DB queries on invalid signatures.
- **3-Stage Free-Text Cascade:** Graceful intent extraction falling back from RapidFuzz string distance to TF-IDF semantic search, then OpenRouter LLM extraction equipped with Pydantic `extra="forbid"` injection guards.
- **Lock-Free Batch Expiries:** Batch background operations (TTL releases, PDPA data purges) employ `SELECT ... FOR UPDATE SKIP LOCKED` for reliable worker parallelism.
- **Deterministic Time Injection:** Every timeout, TTL, and escalation tier supports explicit `now_fn` time injection, enabling 138 lightning-fast tests with zero brittle `time.sleep()` calls.
- **PDPA Privacy by Design:** Implements Article 30/33 right-to-delete compliance; wipes address books entirely and retains historical ledger orders with SHA-256 salted and anonymized `line_user_id` hashes.
- **Air-Gapped Address Processing:** The ThaiSmartAddress parsing engine executes 100% locally and offline—buyer PII (names, phone numbers, addresses) never leaves the host server.

---

## Quick Start (Local Development)

### 1. Clone Repository
```bash
git clone https://github.com/YOUR_USERNAME/KhaiFlow.git
cd KhaiFlow
```

### 2. Backend Setup
```bash
cd backend
cp .env.example .env  # fill in your configuration or local DB credentials
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### 3. Portal Setup
```bash
cd ../portal
cp .env.example .env.local
npm install
npm run dev
```

### 4. Run Test Suites
```bash
# Backend CI verification (secret scan, i18n lint, migrations, ruff, mypy, 124 pytest tests)
make ci

# Frontend Vitest suite (14 portal tests)
npm test
```

### 5. Seed Demo Data (Optional)
Populate your local or staging database with sample inventory items, saved address books, fulfilled orders, and active reservations:
```bash
python scripts/seed_demo.py
```

---

## Environment Variables

| Variable | Group | Description | Required? |
|---|---|---|---|
| `DATABASE_URL` | Database | PostgreSQL connection string (`postgresql://user:pass@host:port/db`) | **Required** |
| `DEFAULT_SHOP_ID` | Tenancy | Default tenant identifier for single-shop operations | Optional (default: `default`) |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE | Channel access token from LINE Developers Console | **Required** |
| `LINE_CHANNEL_SECRET` | LINE | Channel secret used to verify webhook signatures | **Required** |
| `OPENROUTER_API_KEY` | LLM | API key for OpenRouter models (Gemini Flash, GPT-4o-mini) | Required if LLM enabled |
| `LLM_ENABLED` | LLM | Global toggle for LLM intent routing and extraction | Optional (default: `true`) |
| `LLM_MODEL_MAIN` | LLM | Primary LLM model identifier for intent extraction | Optional (default: `gemini/gemini-flash`) |
| `LLM_MODEL_BACKUP` | LLM | Secondary fallback LLM model identifier | Optional (default: `openai/gpt-4o-mini`) |
| `LLM_ESCALATE_CONFIDENCE` | LLM | Confidence threshold before escalating to LLM | Optional (default: `0.8`) |
| `GOOGLE_SERVICE_ACCOUNT_JSON_PATH`| Google | Filesystem path to Google Cloud service account key | Optional |
| `GOOGLE_SHEET_ID` | Google | Target Google Sheet ID for catalog and fulfillment sync | Optional |
| `GOOGLE_SHEET_INVENTORY_RANGE` | Google | Tab and cell range for inventory catalog sync | Optional (default: `Inventory!A1:G`) |
| `SHEET_SYNC_INTERVAL_SECONDS` | Sync | Polling interval in seconds for Google Sheets ingest | Optional (default: `60`) |
| `SHEET_INGEST_SELLER_OVERRIDE` | Sync | Allows genuine sheet edits to override portal catalog | Optional (default: `true`) |
| `CACHE_TTL_SECONDS` | Cache | Read-only inventory cache TTL in seconds | Optional (default: `60`) |
| `PAYMENT_QR_SECRET` | Payment | Secret key used for signing PromptPay QR HMAC hashes | **Required** |
| `GATEWAY_WEBHOOK_SECRET` | Payment | Secret used to authenticate bank/gateway webhooks | **Required** |
| `PAYMENT_TOLERANCE_TYPE` | Payment | Tolerance evaluation mode (`abs` for THB or `pct`) | Optional (default: `abs`) |
| `PAYMENT_TOLERANCE_VALUE` | Payment | Maximum allowable variance for order payments | Optional (default: `1`) |
| `UNDERPAYMENT_POLICY` | Payment | Policy for underpayments (`topup`, `reduce`, `partial_refund`) | Optional (default: `topup`) |
| `OVERPAYMENT_POLICY` | Payment | Policy for overpayments (`refund_diff`, `store_credit`) | Optional (default: `refund_diff`) |
| `VERIFICATION_MODE` | Verification | Verification model (`A` = gateway auto, `B` = manual review) | Optional (default: `B`) |
| `FILTER_C_ENABLED` | Verification | Pre-check gate for CRC, TLV, and slip re-use prevention | Optional (default: `true`) |
| `C_AUTOCONFIRM_ENABLED` | Verification | Opt-in automated payment slip confirmation without human review | Optional (default: `false`) |
| `C_AUTOCONFIRM_PER_ORDER_CAP` | Verification | Maximum order value in THB eligible for auto-confirm | Optional (default: `500`) |
| `C_AUTOCONFIRM_PER_BUYER_DAILY_THB` | Verification | Daily aggregate auto-confirm limit per buyer | Optional (default: `1500`) |
| `C_AUTOCONFIRM_PER_BUYER_DAILY_COUNT` | Verification | Daily maximum auto-confirmed transactions per buyer | Optional (default: `3`) |
| `C_AUTOCONFIRM_PER_SHOP_DAILY_THB` | Verification | Daily shop-wide aggregate auto-confirm limit | Optional (default: `20000`) |
| `C_AUTOCONFIRM_PER_SHOP_DAILY_COUNT` | Verification | Daily shop-wide count of auto-confirmed transactions | Optional (default: `100`) |
| `C_AUTOCONFIRM_COOLDOWN_MINUTES` | Verification | Cooldown period between auto-confirmations for a buyer | Optional (default: `30`) |
| `C_AUTOCONFIRM_AUDIT_SAMPLE_PCT` | Verification | Percentage of auto-confirmed orders routed to human audit | Optional (default: `10`) |
| `C_AUTOCONFIRM_KILLSWITCH_FLAGS` | Verification | Anomaly flags in 24h before auto-confirm killswitch triggers | Optional (default: `3`) |
| `HUMAN_APPROVAL_THRESHOLD` | Verification | Amount in THB above which orders mandate human review | Optional (default: `1000`) |
| `AUTO_APPROVE_SMALL_VIA_A_CAP` | Verification | Maximum amount for auto-confirming gateway payments | Optional (default: `500`) |
| `ESC_REMINDER_MINUTES` | Escalation | Elapsed minutes before first merchant review reminder | Optional (default: `10`) |
| `ESC_URGENT_BACKUP_MINUTES` | Escalation | Elapsed minutes before alerting backup merchant contact | Optional (default: `15`) |
| `ESC_AUTO_ACTION_MINUTES` | Escalation | Elapsed minutes before auto-action triggers on unattended orders | Optional (default: `30`) |
| `ESC_HARD_CEILING_HOURS` | Escalation | Absolute deadline in hours before cancelling unconfirmed orders | Optional (default: `24`) |
| `RESERVATION_TTL_SECONDS` | Stock | Time temporary cart holds remain valid before address confirmation | Optional (default: `600`) |
| `TTL_AWAITING_PAYMENT_MINUTES` | Stock | Order payment window before stock reservation is released | Optional (default: `30`) |
| `TTL_REVIVAL_CONFIRM_MINUTES` | Stock | Allowable re-reservation window on late payment receipt | Optional (default: `10`) |
| `SESSION_TTL_HOURS` | Portal Auth | Seller portal authentication session validity duration | Optional (default: `12`) |
| `LOGIN_RATE_LIMIT` | Portal Auth | Maximum portal login rate before temporary account lockout | Optional (default: `5/min`) |
| `MFA_ENABLED` | Portal Auth | Multi-Factor Authentication enforcement switch | Optional (default: `false`) |
| `RETENTION_MONTHS` | PDPA | Months before inactive buyer records are flagged for deletion | Optional (default: `12`) |
| `CONSENT_REQUIRED` | PDPA | Require explicit PDPA consent before cart creation | Optional (default: `true`) |
| `INTEGRITY_JOB_INTERVAL_MINUTES` | Ops | Frequency of background stock invariant reconciliation job | Optional (default: `60`) |
| `CARRIER_CONFIGS` | Export | JSON configuration mapping custom courier CSV schemas | Optional (default: `{}`) |
| `EXPORT_INCLUDE_STATUSES` | Export | Comma-separated order statuses included in fulfillment export | Optional (default: `confirmed,fulfilled`) |
| `CAROUSEL_PAGE_SIZE` | UX | Maximum items rendered per LINE carousel page | Optional (default: `8`) |
| `ADDRESS_BOOK_ENABLED` | UX | Multi-address saved address book feature toggle | Optional (default: `true`) |
| `UI_DEFAULT_BUYER_LANGUAGE` | UX | Default buyer language code (`th` or `en`) | Optional (default: `th`) |
| `UI_BUYER_LANGUAGE_SELECTABLE` | UX | Allow buyers to switch between Thai and English | Optional (default: `true`) |
| `UI_DEFAULT_PORTAL_LANGUAGE` | UX | Default language for seller portal (`en` or `th`) | Optional (default: `en`) |
| `UI_DEFAULT_THEME` | UX | Default theme mode for portal (`system`, `light`, `dark`) | Optional (default: `system`) |
| `UI_THEME_SELECTABLE` | UX | Allow sellers to toggle portal color theme | Optional (default: `true`) |
| `NEXT_PUBLIC_API_BASE_URL` | Portal | Public backend REST API URL accessed by portal | **Required for Portal** |

---

## Project Structure

```
KhaiFlow/
├── backend/
│   ├── alembic/              # Database migration versions (Phases 1–10)
│   ├── app/                  # FastAPI routers, models, schemas, and services
│   ├── tests/                # 124 pytest test suites covering all phases
│   ├── .env.example          # Authoritative backend environment variables
│   └── requirements.txt      # Python runtime dependencies
├── portal/
│   ├── app/                  # Next.js App Router (auth, dashboard, inventory, orders)
│   ├── components/           # Reusable UI widgets with full dark mode support
│   ├── context/              # React context for theme and i18n state
│   ├── lib/                  # Type-safe API client and auth helpers
│   ├── locale/               # Bilingual EN/TH translation keys (100% parity)
│   ├── __tests__/            # 14 Vitest unit and integration tests
│   └── .env.example          # Portal frontend environment template
├── scripts/
│   ├── check_no_secrets.sh   # Pre-commit secret scanning script
│   ├── i18n_lint.sh          # Translation key parity validator
│   ├── migration_check.sh    # Database schema drift detector
│   ├── phase_evidence.sh     # Phase evidence collector
│   └── seed_demo.py          # Idempotent demo database populator
├── DEPLOYMENT.md             # Production deployment guide (Railway + Vercel)
├── Makefile                  # Automated CI, test, lint, and build targets
└── README.md                 # System overview and developer guide
```

---

## Deployment

Refer to [`DEPLOYMENT.md`](DEPLOYMENT.md) for full step-by-step production deployment instructions covering:
- Managed PostgreSQL and FastAPI deployment on **Railway**
- Next.js App Router deployment on **Vercel**
- LINE Developer Console webhook configuration and Rich Menu provisioning
- Health checks and production monitoring

---

## License

This project is licensed under the terms of the [MIT License](LICENSE).
