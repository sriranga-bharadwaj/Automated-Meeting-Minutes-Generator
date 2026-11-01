# AMMG Frontend (React + TypeScript + Vite)

Flow: Create meeting -> Upload or record audio -> Processing status -> Edit minutes -> Export.

## Run
    npm install
    npm run dev          # http://localhost:5173, demo mode (built-in mock backend)

Tip: upload a file with "fail" in its name (e.g. fail.mp3) to see the error and Retry path.

## Use the real FastAPI backend
    cp .env.example .env     # set VITE_USE_MOCK=false
    uvicorn app.main:app --port 8000   # Vite proxies /api to localhost:8000

Endpoints the UI calls (adjust src/api.ts if Member 1's paths differ):
POST /api/v1/meetings, POST /meetings/{id}/audio, GET /meetings/{id}/status, POST /meetings/{id}/retry,
GET /meetings/{id}/minutes, PUT /minutes/{id}, POST /minutes/{id}/export

## Tests and reports
    npm test             # unit tests
    npm run coverage     # statements, branches, lines (HTML in coverage/)
    npm run build
