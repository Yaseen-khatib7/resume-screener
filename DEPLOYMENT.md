# Deployment

## Recommended layout

- Frontend: Vercel
- Backend: Render

This keeps the app running in the cloud instead of on your personal computer.

## Backend on Render

The backend uses:

- `backend/storage` for ATS/session files
- `models/registry.json` for model registry
- `models/finetuned` for trained models
- `models/hf-cache` when Hugging Face assets are cached locally

The included [render.yaml](/C:/Users/mrkha/OneDrive/Desktop/resume-screening-model/render.yaml) already configures a persistent disk mounted at `/var/data`.

Persistent paths used by the deployed app:

- `/var/data/backend-storage`
- `/var/data/models/registry.json`
- `/var/data/models/finetuned`
- `/var/data/models/hf-cache`

Then set these environment variables on Render:

- `FIREBASE_SERVICE_ACCOUNT_JSON`
- `BOOTSTRAP_ADMIN_EMAILS`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_EMAIL`
- `SMTP_FROM_NAME`
- `SMTP_USE_TLS`
- `GITHUB_OPENAI_KEY` or `GITHUB_TOKEN`
- `GITHUB_MODELS_CHAT_MODEL=openai/gpt-4.1-nano`
- `GITHUB_MODELS_TIMEOUT_SECONDS=10`
- optional: `HF_TOKEN`

Create the Render web service from the repo root using [render.yaml](/C:/Users/mrkha/OneDrive/Desktop/resume-screening-model/render.yaml).

Build command:

```powershell
pip install -r requirements.txt
```

Start command:

```powershell
python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

## Frontend on Vercel

Deploy the `frontend` directory as a Vite app.

Set these environment variables in Vercel:

- `VITE_API_BASE_URL`
- `VITE_FIREBASE_API_KEY`
- `VITE_FIREBASE_AUTH_DOMAIN`
- `VITE_FIREBASE_PROJECT_ID`
- `VITE_FIREBASE_STORAGE_BUCKET`
- `VITE_FIREBASE_MESSAGING_SENDER_ID`
- `VITE_FIREBASE_APP_ID`

Use [frontend/.env.production.example](/C:/Users/mrkha/OneDrive/Desktop/resume-screening-model/frontend/.env.production.example) as the template.

## Important note about storage

Cloud storage on Render does not affect your personal computer. Once deployed, the backend runs on Render's infrastructure. Files written by the deployed app stay on the Render instance or attached Render disk, not on your laptop.

Your local machine is only affected if you run the backend locally.
