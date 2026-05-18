# Pakistan Orbit Tracker

This project is a React + Vite frontend for live satellite tracking over Pakistan.

## Python Backend

A Python backend has been added under `backend/` to proxy CelesTrak TLE data and avoid browser CORS issues.

### Install Python dependencies

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Run backend

```bash
cd backend
.\.venv\Scripts\activate
uvicorn main:app --reload --host 127.0.0.1 --port 8001
```

### Frontend development

From the project root:

```bash
npm install
npm run dev
```

The frontend runs at `http://localhost:8080` and proxies `/api/*` requests to the backend at `http://127.0.0.1:8001`.

Or just run `start.bat` from the project root to launch both at once.

### Available backend endpoints

- `GET /api/health` - health check
- `GET /api/categories` - satellite category metadata
- `GET /api/tle?category=<category>` - fetch raw TLE data for a category
