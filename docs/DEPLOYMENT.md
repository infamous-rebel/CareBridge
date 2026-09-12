# CareBridge Deployment Guide

Step-by-step runbook for deploying CareBridge to production.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Railway Backend Deploy](#railway-backend-deploy)
- [Vercel Frontend Deploy](#vercel-frontend-deploy)
- [Firebase Setup](#firebase-setup)
- [CORS Configuration](#cors-configuration)
- [Common Failure Modes](#common-failure-modes)

---

## Prerequisites

- GitHub repo pushed and accessible
- Railway account (https://railway.app)
- Vercel account (https://vercel.com) linked to the GitHub org
- Firebase project created (https://console.firebase.google.com)
- LLM provider API key (Gemini free tier: https://aistudio.google.com/apikey)

---

## Railway Backend Deploy

### 1. Create the Railway project

1. Go to https://railway.app → **New Project** → **Deploy from GitHub repo**.
2. Select the CareBridge repository.
3. Railway auto-detects the Dockerfile. Confirm the settings:
   - **Builder:** Nixpacks or Dockerfile (Dockerfile preferred — it's already configured)
   - **Start Command:** `uvicorn src.api.main:app --host 0.0.0.0 --port $PORT`

### 2. Environment Variables (18 vars)

Add these in **Variables** → **Raw Editor** or one-by-one:

| Variable | Value | Notes |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | Or `groq`, `bedrock`, `anthropic`, `openai`, `ollama`, `litellm` |
| `GEMINI_API_KEY` | *(your key)* | Required when LLM_PROVIDER=gemini |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Or another Gemini model |
| `JWT_SECRET_KEY` | *(random ≥32 bytes)* | Generate: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | |
| `BCRYPT_ROUNDS` | `12` | |
| `ENVIRONMENT` | `production` | |
| `DEMO_MODE` | `true` | Set `false` in real production |
| `DEMO_USER_EMAIL` | `demo@carebridge.local` | |
| `DEMO_USER_PASSWORD` | `CareBridgeDemo!2026` | |
| `DEMO_USER_ROLE` | `caregiver_primary` | |
| `CORS_ORIGINS` | `https://care-bridge-sable-one.vercel.app` | Your Vercel domain |
| `AUDIT_DB_PATH` | `/tmp/audit.db` | **Required** — Railway containers are read-only |
| `AUTH_DB_PATH` | `/tmp/auth.db` | Same reason |
| `FIREBASE_AUTH_ENABLED` | `true` | |
| `FIREBASE_PROJECT_ID` | `carebridge-675df` | Your Firebase project |
| `FIREBASE_CREDENTIALS_B64` | *(base64 service account)* | See Firebase Setup below |

**Optional vars:**

| Variable | Default | Notes |
|---|---|---|
| `AUTH_RATE_LIMIT` | `60/minute` | |
| `GLOBAL_RATE_LIMIT` | `300/minute` | |
| `MAX_REQUEST_BYTES` | `1048576` | 1MB |
| `JSON_LOGGING` | `true` | Structured JSON logs |
| `LOG_LEVEL` | `INFO` | |
| `DATABASE_URL` | *(not set)* | Set when using PostgreSQL |

### 3. Generate FIREBASE_CREDENTIALS_B64

```bash
python3 -c "
import base64
with open('secrets/firebase-service-account.json', 'rb') as f:
    print(base64.b64encode(f.read()).decode())
"
```

Paste the output as the value of `FIREBASE_CREDENTIALS_B64`. This is preferred over `FIREBASE_SERVICE_ACCOUNT_PATH` on Railway because Railway mangles PEM newlines in raw JSON env vars.

### 4. Deploy

Click **Deploy**. Railway builds the Docker image and starts the container. The health check hits `/health` every 30s.

Verify:
```bash
curl https://carebridge-production-4bd1.up.railway.app/health
# → {"status":"ok"}

curl https://carebridge-production-4bd1.up.railway.app/ready
# → {"status":"ok","checks":{"audit_db":true,"mcp_registry":true},"llm_provider":"gemini","llm_available":true}
```

---

## Vercel Frontend Deploy

### 1. Import the project

1. Go to https://vercel.com/new → **Import Git Repository**.
2. Select the CareBridge repository.
3. **Important:** Set **Root Directory** to `src/ui`.
4. Vercel auto-detects Next.js. Framework Preset: **Next.js**.

### 2. Environment Variables (8 vars)

Add these in **Settings** → **Environment Variables**:

| Variable | Value | Notes |
|---|---|---|
| `NEXT_PUBLIC_FIREBASE_API_KEY` | *(from Firebase console)* | |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | `carebridge-675df.firebaseapp.com` | |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | `carebridge-675df` | |
| `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET` | `carebridge-675df.firebasestorage.app` | |
| `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID` | *(from Firebase console)* | |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | *(from Firebase console)* | |
| `NEXT_PUBLIC_DEMO_MODE` | `true` | Shows demo credentials on login |
| `NEXT_PUBLIC_API_URL` | `https://carebridge-production-4bd1.up.railway.app` | Backend URL |

### 3. Deploy

Click **Deploy**. Vercel builds and assigns a domain.

Verify:
- Open the Vercel URL → login page renders
- Click "Try as demo caregiver" → dashboard loads

---

## Firebase Setup

### 1. Create a Firebase project

1. Go to https://console.firebase.google.com → **Add project**.
2. Name it (e.g., `carebridge-675df`).
3. Enable or disable Google Analytics (optional).

### 2. Enable Google OAuth

1. **Authentication** → **Sign-in method** → **Google** → Enable.
2. Set a support email and project public name.
3. Add authorized domains:
   - `care-bridge-sable-one.vercel.app`
   - `localhost` (for local dev)

### 3. Generate a service account key

1. **Project Settings** → **Service accounts** → **Generate new private key**.
2. Download the JSON file.
3. Save it as `secrets/firebase-service-account.json` (for local dev).
4. Base64-encode it for Railway (see step 3 above).

### 4. Register a web app

1. **Project Settings** → **Your apps** → **Add app** → Web (`</>`).
2. Copy the `firebaseConfig` object values into the Vercel env vars.

### 5. Authorized domains

1. **Authentication** → **Settings** → **Authorized domains**.
2. Add your Vercel domain: `care-bridge-sable-one.vercel.app`.

---

## CORS Configuration

The backend CORS middleware reads `CORS_ORIGINS` from the environment. Set it to a comma-separated list of allowed origins:

```
CORS_ORIGINS=https://care-bridge-sable-one.vercel.app,http://localhost:3000
```

For production, include only the Vercel domain. For local development, include `http://localhost:3000`.

The backend allows credentials (`allow_credentials=True`) and all methods/headers. The `X-Request-ID` header is exposed to the browser.

---

## Common Failure Modes

### Firebase 503 — `FIREBASE_CREDENTIALS_B64` invalid

**Symptom:** `POST /auth/firebase/exchange` returns 503 "Firebase authentication is not configured".

**Cause:** The base64-encoded service account JSON is malformed, or the env var is not set.

**Fix:**
1. Verify the env var is set: `railway variables get FIREBASE_CREDENTIALS_B64`
2. Re-encode the service account:
   ```bash
   python3 -c "
   import base64, json
   with open('secrets/firebase-service-account.json', 'rb') as f:
       raw = f.read()
   # Verify it's valid JSON
   json.loads(raw)
   print(base64.b64encode(raw).decode())
   "
   ```
3. Update the Railway variable and redeploy.

### audit_db false — `AUDIT_DB_PATH` missing

**Symptom:** `GET /ready` returns `{"status":"degraded","checks":{"audit_db":false,...}}`.

**Cause:** The container filesystem is read-only and `AUDIT_DB_PATH` is not set (defaults to `./audit.db`).

**Fix:** Set `AUDIT_DB_PATH=/tmp/audit.db` in Railway variables. Also set `AUTH_DB_PATH=/tmp/auth.db`. Redeploy.

### LLM 429 — Provider quota exhausted

**Symptom:** `GET /ready` returns `llm_available: false`. `/query` returns 503 "Supervisor agent runtime unavailable".

**Cause:** The LLM provider's rate limit or quota has been exceeded.

**Fix:**
1. Check the provider's dashboard (e.g., Google AI Studio for Gemini).
2. Switch to a different provider: change `LLM_PROVIDER` and set the new provider's API key.
3. Restart the Railway service.

### Model 404 — Model name wrong

**Symptom:** LLM calls fail with a 404 or "model not found" error.

**Cause:** The model name in `GEMINI_MODEL`, `GROQ_MODEL`, etc. is incorrect or deprecated.

**Fix:**
| Provider | Correct model names |
|---|---|
| Gemini | `gemini-2.5-flash`, `gemini-2.5-pro` |
| Groq | `llama-3.3-70b-versatile`, `mixtral-8x7b-32768` |
| Bedrock | `anthropic.claude-sonnet-4-20250514-v1:0` |
| Anthropic | `claude-sonnet-4-20250514` |
| OpenAI | `gpt-4o-mini`, `gpt-4o` |

Update the model var and restart.

### Frontend login loop — CORS or API URL mismatch

**Symptom:** Login succeeds but the dashboard immediately redirects back to login.

**Cause:** The frontend's `NEXT_PUBLIC_API_URL` doesn't match the backend's `CORS_ORIGINS`, or the API is unreachable.

**Fix:**
1. Verify `NEXT_PUBLIC_API_URL` in Vercel env vars matches the Railway URL exactly (including `https://`).
2. Verify `CORS_ORIGINS` in Railway includes the Vercel domain.
3. Check the browser console for CORS errors.

### Demo user not found — DEMO_MODE mismatch

**Symptom:** Login with demo credentials returns 401.

**Cause:** `DEMO_MODE` is `false` on the backend, so the demo user was never seeded.

**Fix:** Set `DEMO_MODE=true` in Railway variables and redeploy. Or create a real user via the auth flow.
