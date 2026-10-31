# 🚀 FormPilot — Live Deployment & Multi-Site Guide

This guide explains how to take **both sites live**, deploy the Mock Government Portal to **Vercel**, deploy FormPilot, and connect them with a 1-click test link.

---

## 🏗️ Architecture: The Two Sites Explained

```
┌────────────────────────────────────────────────────────┐
│ SITE 2: GOV PORTAL SIMULATOR (Standalone Test Portal)  │
│ Hosted on: VERCEL (100% Free, Static / Serverless)     │
│ URL: https://demo-gov-portal.vercel.app                │
└───────────────────────────▲────────────────────────────┘
                            │
              (Forms navigated & observed)
                            │
┌───────────────────────────┴────────────────────────────┐
│ SITE 1: FORMPILOT APPLICATION ASSISTANT                │
│                                                        │
│  A. Frontend Cockpit (React 19 + Vite)                 │
│     Hosted on: VERCEL                                  │
│     URL: https://formpilot.vercel.app                  │
│                                                        │
│  B. Automation Engine & WebSockets (FastAPI + CDP)     │
│     Hosted on: RENDER / RAILWAY / DOCKER               │
│     URL: https://formpilot-backend.onrender.com        │
└────────────────────────────────────────────────────────┘
```

---

## 📌 STEP 1: Deploy Site 2 (Gov Portal Simulator) on Vercel

The folder `gov-portal-site/` is completely standalone, with an interactive client-side mock for:
- New Registration / OTR flow
- Instant OTP generation (code `492015` shown on-screen)
- Permanent OTR ID creation (`FP-2026-XXXXXX`) stored in `localStorage`
- Candidate login and dashboard
- Zero external dependencies!

### Option A: Via GitHub & Vercel Dashboard (Recommended)
1. Initialize a new repo for the portal:
   ```bash
   cd gov-portal-site
   git init
   git add .
   git commit -m "Initial commit of Gov Portal Simulator"
   git branch -M main
   # Create a repo on github.com/new named 'gov-portal-simulator'
   git remote add origin https://github.com/YOUR_USERNAME/gov-portal-simulator.git
   git push -u origin main
   ```
2. Go to **[vercel.com/new](https://vercel.com/new)**.
3. Import your `gov-portal-simulator` repository.
4. Framework Preset: **Other** (Root directory: `.`).
5. Click **Deploy**.
6. You now have a live URL! *(e.g., `https://gov-portal-simulator.vercel.app`)*

### Option B: Via Vercel CLI (Instant)
```bash
cd gov-portal-site
npx vercel
```
Follow the prompts (accept default settings).

---

## 📌 STEP 2: Deploy Site 1 (FormPilot Backend Engine)

> **Why the Backend cannot run on Vercel Serverless:**
> FormPilot streams live browser frames at 15–30 FPS over bidirectional **WebSockets** (`/ws/live` and `/ws/cockpit`) and drives a headless Chromium instance (Playwright). Vercel Serverless terminates connections after 10–60 seconds and does not support persistent WebSockets or long-running Chromium processes.
> 
> Therefore, the backend runs on container platforms like **Render**, **Railway**, or **Fly.io** (all offer free/cheap hosting).

### Deploying on Render (Free Tier):
1. Push this entire repository (`hackthon`) to a GitHub repository.
2. Go to **[dashboard.render.com](https://dashboard.render.com)** $\rightarrow$ Click **New +** $\rightarrow$ **Web Service**.
3. Select your repository.
4. Render will automatically detect the `Dockerfile` and `render.yaml`.
5. Environment Variables to add:
   * `FORMPILOT_ENV` = `production`
   * `FORMPILOT_DEMO_MODE` = `1`
   * `FORMPILOT_CORS_ORIGINS` = `*` (or your Vercel URL)
6. Click **Create Web Service**.
7. Note down your backend URL: e.g. `https://formpilot-backend.onrender.com`.

*(Alternatively on Railway: simply click "New Project" -> "Deploy from GitHub repo" and Railway auto-detects `railway.json` and `Dockerfile`)*.

---

## 📌 STEP 3: Deploy Site 1 (FormPilot Frontend) on Vercel

1. In your Vercel Dashboard, click **Add New...** $\rightarrow$ **Project**.
2. Select your `hackthon` repository.
3. Set **Root Directory** to `frontend`.
4. Framework Preset: **Vite**.
5. Under **Environment Variables**, add:
   * `VITE_API_BASE_URL` = `https://your-backend-url.onrender.com` (from Step 2)
   * `VITE_PRACTICE_PORTAL_URL` = `https://your-gov-portal.vercel.app` (from Step 1)
6. Click **Deploy**.
7. Your friends can now visit `https://formpilot.vercel.app` from anywhere in the world!

---

## 📌 STEP 4: Testing the Live Experience with Friends

Once deployed:
1. Open your FormPilot live link (`https://formpilot.vercel.app`).
2. Right below the search bar, you and your friends will see the new banner:
   > 🟢 **Test Portal Ready:** Practice safely without touching real government portals.  
   > `[Load in Assistant]` `[Open Site ↗]`
3. Clicking **Load in Assistant** automatically loads your live Vercel Gov Portal URL into the input.
4. Clicking **Open Site ↗** opens the mock portal in a separate browser tab so your friends can watch both sites side-by-side!
5. Hit **Start Application** $\rightarrow$ FormPilot will navigate the live portal, fill the fields from the vault, and pause safely at the OTP and pre-payment gates!
