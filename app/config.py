import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
PORT = int(os.getenv("PORT", "5174"))
WEB_ORIGIN = os.getenv("WEB_ORIGIN", "http://localhost:5173")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-me")
NODE_ENV = os.getenv("NODE_ENV", "development")
SESSION_HTTPS_ONLY = os.getenv("SESSION_HTTPS_ONLY", "").strip().lower() in {
    "1",
    "true",
    "yes",
} or WEB_ORIGIN.startswith("https://")


def resolve_sqlite_path() -> Path:
    raw = os.getenv("SQLITE_PATH", "").strip()
    if raw:
        return Path(raw)
    if NODE_ENV == "production":
        render_disk = Path("/var/data")
        if render_disk.exists():
            return render_disk / "uni-q.sqlite"
    return BASE_DIR / "data" / "uni-q.sqlite"


SQLITE_PATH = resolve_sqlite_path()
DIST_DIR = BASE_DIR / "dist"
PUBLIC_DIR = BASE_DIR / "public"
FLAPPY_DIR = BASE_DIR / "flappy bird"
CHAT_KB_XLSX_PATH = Path(
    os.getenv(
        "UNIQ_CHAT_KB_XLSX_PATH",
        str(BASE_DIR / "chat_bot" / "1300_вопросов_от_студентов_для_базы_данных.xlsx"),
    )
)

UNIQ_NVIDIA_API_KEY = os.getenv("UNIQ_NVIDIA_API_KEY", "").strip()
UNIQ_NVIDIA_CHAT_MODEL = os.getenv("UNIQ_NVIDIA_CHAT_MODEL", "nvidia/nvidia-nemotron-nano-9b-v2").strip()
UNIQ_NVIDIA_API_BASE = os.getenv("UNIQ_NVIDIA_API_BASE", "https://integrate.api.nvidia.com/v1").rstrip("/")
