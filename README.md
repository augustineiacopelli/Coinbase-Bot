# Coinbase Always‑On Bot (FastAPI + OpenAI Agent)

A minimal, production‑oriented FastAPI service you can deploy to Render, Railway, or Google Cloud Run.
It exposes:
- `GET /health` – health check
- `GET /price/{product_id}` – live price from Coinbase Advanced Trade (e.g., BTC-USD)
- `POST /watchlist` – body: {"symbols": ["BTC-USD","ETH-USD"]}
- `POST /chat` – simple OpenAI agent that can call the price tool

## 1) Local Dev

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # fill in your keys
uvicorn app.main:app --reload
```

Visit: http://127.0.0.1:8000/docs

## 2) Environment Variables

Copy `.env.example` to `.env` locally (never commit real secrets):
- `COINBASE_API_KEY`
- `COINBASE_API_SECRET`
- `OPENAI_API_KEY`

On your cloud host, set these in the dashboard (Render/Railway/Cloud Run).

## 3) Deploy Options

### Render.com (easy)
1. Push to GitHub.
2. Create new **Web Service** on Render → connect repo.
3. Runtime: Docker (auto-detected from `Dockerfile`), or use **Python** and the `Procfile`:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables in Render dashboard.

### Railway.app
1. New project → Deploy from GitHub.
2. Add environment variables.
3. It will detect Python; otherwise set start command:
   ```
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```

### Google Cloud Run (serverless)
```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/coinbase-bot
gcloud run deploy coinbase-bot --image gcr.io/PROJECT_ID/coinbase-bot --platform managed --allow-unauthenticated --set-env-vars OPENAI_API_KEY=...,COINBASE_API_KEY=...,COINBASE_API_SECRET=...
```

## 4) Safety Notes
- Start with market‑data only. No trading calls are implemented here.
- If you add trading: implement paper‑mode, position caps, audit log, and a kill switch.
