# uni-q 2.0

Python/FastAPI rewrite of the uni-q queue server.

## Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:socket_app --host 0.0.0.0 --port 5174 --reload
```

Open: http://localhost:5174/

The server uses `data/uni-q.sqlite` by default and serves the copied Vite `dist/` build.
