# CareBridge Frontend

Production-grade Next.js 15 caregiver dashboard for the CareBridge care-coordination platform.

## Quick Start

```bash
npm install
cp .env.local.example .env.local
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Demo Credentials

When `NEXT_PUBLIC_DEMO_MODE=true` (default in `.env.local.example`):
- Email: `demo@carebridge.local`
- Password: `demo1234`

## Build

```bash
npm run build    # production build
npm run lint     # ESLint
```

## Architecture

- **App Router** — `app/` directory with nested layouts
- **TypeScript strict** — `noUncheckedIndexedAccess`, no `any`
- **Tailwind CSS v4** — soft mint palette matching UX reference
- **TanStack Query** — server-state caching + auto-refetch
- **Framer Motion** — scroll-triggered animations
- **zod** — runtime API response validation

## API Proxy

The dev server rewrites `/api/*` → `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).
The FastAPI backend must be running for authenticated pages to load real data.
