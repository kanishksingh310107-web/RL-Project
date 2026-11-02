# Main entry point to run the app
import uvicorn
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.api import router
from app.modules import discover, init_module_tables, registry_router

app = FastAPI(title="RL Travel Guide")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(registry_router)
for _m in discover():
    app.include_router(_m.router)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.on_event("startup")
def startup():
    init_db()
    init_module_tables()

@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")

if __name__ == "__main__":
    print("Running on http://localhost:8000")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
