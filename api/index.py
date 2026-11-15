# Vercel entrypoint: every request is rewritten here (vercel.json) and served by FastAPI.
from app.main import app  # noqa: F401
