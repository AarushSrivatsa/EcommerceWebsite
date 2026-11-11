# Script to Video — frontend

Vue 3 + TypeScript + Vite + Tailwind. Talks to the FastAPI backend in the repo root.

## Run

1. Backend (repo root, with `.env` filled in: DATABASE_URL, GROQ_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY, API_KEY):
   `uvicorn main:app --reload --port 8000`
2. Frontend:
   `cd frontend && npm install && npm run dev` → http://localhost:5173

`npm run dev` proxies the API calls to `http://localhost:8000`. In production nothing to configure: the backend serves the built app (`npm run build` -> `dist/`) from the same address.

## Where the API lives
Everything backend-specific is in `src/services/projectService.ts` (endpoints + snake_case mapping) and `src/services/api.ts` (fetch wrapper).

## Notes
- Nothing is rendered automatically. After the script is written you edit it, add images, then press **Build section videos** (`POST /scripts/{id}/render_sections`) to see each section's video, and **Generate final video** (`POST /convert_into_video/{id}`) to join them. Each section also has its own Build / Rebuild button.
