# Production Deployment Guide: KhaiFlow LINE Commerce Bot

This guide provides a comprehensive, step-by-step walkthrough for deploying the **KhaiFlow LINE Commerce System** to production using **Railway** (FastAPI backend + Managed PostgreSQL) and **Vercel** (Next.js Seller Portal).

---

## 1. Prerequisites

Before starting, ensure you have active accounts and credentials for the following services:

| Service | Requirement | Purpose |
|---|---|---|
| **Railway** | Account & Project | Hosts FastAPI backend + managed PostgreSQL |
| **Vercel** | Account | Hosts Next.js Seller Portal frontend |
| **LINE Developers Console** | Messaging API Channel | Webhook ingestion and buyer messaging |
| **OpenRouter** | API Key | LLM router and free-text intent extraction |
| **Google Cloud** *(Optional)* | Service Account JSON + Sheet ID | Google Sheets catalog and fulfillment sync |

---

## 2. Infrastructure Setup & Backend on Railway

### 2.1 Provision PostgreSQL Database
1. Log in to [Railway](https://railway.app/).
2. Click **New Project** → **Provision PostgreSQL**.
3. Once provisioned, navigate to the PostgreSQL service → **Variables** tab.
4. Copy the `DATABASE_URL` (or `DATABASE_PUBLIC_URL` for local migrations).
   > **Note on Protocol:** SQLAlchemy and psycopg2 require the connection string to begin with `postgresql://`. If Railway provides `postgres://`, update the protocol prefix to `postgresql://`.

### 2.2 Configure Backend Environment Variables
In your Railway project, click **New Service** → **GitHub Repo** → select your `thai-smart-address` repository.
Set the **Root Directory** to `backend`.

Add the following environment variables in the **Variables** tab:

```ini
# Database & Multi-Tenancy
DATABASE_URL=postgresql://postgres:password@postgres.railway.internal:5432/railway
DEFAULT_SHOP_ID=default

# LINE Messaging API
LINE_CHANNEL_ACCESS_TOKEN=your_long_lived_channel_access_token_here
LINE_CHANNEL_SECRET=your_channel_secret_here

# OpenRouter / LLM
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LLM_ENABLED=true
LLM_MODEL_MAIN=gemini/gemini-flash
LLM_MODEL_BACKUP=openai/gpt-4o-mini
LLM_ESCALATE_CONFIDENCE=0.8

# Payment & Security Secrets
PAYMENT_QR_SECRET=generate_a_random_32_byte_secret_here
GATEWAY_WEBHOOK_SECRET=generate_another_32_byte_secret_here

# Verification Policies
VERIFICATION_MODE=B
FILTER_C_ENABLED=true
C_AUTOCONFIRM_ENABLED=false
HUMAN_APPROVAL_THRESHOLD=1000

# Google Sheets Sync (Optional)
GOOGLE_SERVICE_ACCOUNT_JSON_PATH=/app/service_account.json
GOOGLE_SHEET_ID=your_google_sheet_id_here
GOOGLE_SHEET_INVENTORY_RANGE=Inventory!A1:G
```

### 2.3 Set Build & Start Commands
Under **Settings** in the Railway service:
- **Build Command:**
  ```bash
  pip install -r requirements.txt
  ```
- **Deploy Start Command:**
  ```bash
  alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
  ```

### 2.4 Generate Public Domain
Under **Settings** → **Networking** → click **Generate Domain**.
Your backend will be reachable at a URL like:
`https://thai-smart-address-backend-production.up.railway.app`

---

## 3. Configure LINE Developer Console

1. Navigate to the [LINE Developers Console](https://developers.line.biz/console/).
2. Select your Provider and **Messaging API** channel.
3. In the **Messaging API** settings tab:
   - **Webhook URL:** Set to `https://<YOUR-RAILWAY-APP>.up.railway.app/line/webhook`
   - Click **Verify** to test the connection.
   - Toggle **Use webhook** to **Enabled**.
4. In the **LINE Official Account features** section:
   - Auto-reply messages: **Disabled**
   - Greeting messages: **Disabled** (or customize as desired)
   - Webhook: **Enabled**

---

## 4. Seller Portal Deployment on Vercel

The portal is a Next.js 14 App Router application with Tailwind CSS and full internationalization (EN/TH).

### 4.1 Import Repository to Vercel
1. Log in to [Vercel](https://vercel.com/).
2. Click **Add New...** → **Project** → select your `thai-smart-address` repository.
3. Configure project settings:
   - **Framework Preset:** Next.js
   - **Root Directory:** Edit and select `portal`
   - **Build Command:** `npm run build` (default)
   - **Output Directory:** `.next` (default)

### 4.2 Configure Environment Variables
Add the public backend API endpoint:

| Key | Value | Description |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `https://<YOUR-RAILWAY-APP>.up.railway.app` | Base URL for FastAPI REST calls |

### 4.3 Deploy
Click **Deploy**. Once completed, Vercel will assign a production domain (e.g., `https://thai-smart-address-portal.vercel.app`).

---

## 5. Post-Deployment Initialization

### 5.1 Initialize Demo Data (Optional)
To verify your newly deployed database with sample inventory and orders:
```bash
# Run locally with your Railway database connection string
DATABASE_URL="postgresql://postgres:password@your-railway-db.railway.app:5432/railway" \
python scripts/seed_demo.py
```

### 5.2 LINE Rich Menu Setup
After your backend is live, initialize the LINE Rich Menu (bilingual EN/TH) for buyers:
```bash
# From the backend directory with LINE credentials configured in .env:
python -c "
from app.services.rich_menu import build_rich_menu_object
from app.core.line_client import LineClient
client = LineClient()
menu_th = build_rich_menu_object('th')
menu_id = client.create_rich_menu(menu_th)
print(f'Created Thai Rich Menu: {menu_id}')
"
```
You can also use the LINE Official Account Manager UI or curl to upload your rich menu image asset and set it as default.

---

## 6. Health Checks & Verification

Verify each component is responding correctly:

1. **Backend Health Check:**
   ```bash
   curl -s -f https://<YOUR-RAILWAY-APP>.up.railway.app/health
   # Expected output: {"status": "ok"}
   ```

2. **Webhook Signature Security Verification:**
   ```bash
   curl -s -i -X POST https://<YOUR-RAILWAY-APP>.up.railway.app/line/webhook -d '{"events":[]}'
   # Expected output: HTTP 400 Bad Request (missing or invalid X-Line-Signature)
   ```

3. **Portal API Connectivity:**
   Open `https://<YOUR-VERCEL-PORTAL>.vercel.app` in your browser. Inspect the Network tab to confirm calls to `/api/orders` and `/api/inventory` return status 200 with loaded catalog data.

---

## 7. Troubleshooting & Common Issues

### Issue 1: Webhook Signature Mismatch (HTTP 400)
- **Cause:** `LINE_CHANNEL_SECRET` in Railway has trailing whitespace or does not match the channel in LINE Developers Console.
- **Fix:** Copy the channel secret directly from LINE Console and re-save in Railway variables. Ensure no extra spaces or newline characters exist.

### Issue 2: SQLAlchemy Database URL Scheme Error
- **Error:** `NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:postgres`
- **Cause:** Railway's default connection string uses `postgres://` instead of `postgresql://`.
- **Fix:** Update `DATABASE_URL` in Railway to begin with `postgresql://`.

### Issue 3: CORS Errors on Portal Requests
- **Cause:** Origin blocked by FastAPI CORS middleware.
- **Fix:** FastAPI in `app/main.py` is configured with `allow_origins=["*"]` by default. If modified in production, ensure your Vercel deployment domain is included in `allow_origins`.

### Issue 4: Alembic Migration Lock / Failure on Deploy
- **Cause:** Previous deploy crashed or connection was abruptly terminated during migration.
- **Fix:** Check Railway deployment logs. Connect using a DB client (e.g., psql / TablePlus) to `alembic_version` table and verify the current revision.

### Issue 5: Google Sheets 403 Forbidden
- **Cause:** The Google Service Account does not have Editor access to the target Google Sheet.
- **Fix:** Open your Google Sheet → click **Share** → paste the `client_email` from your service account JSON file → grant **Editor** permissions.
