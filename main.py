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

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


if __name__ == "__main__":
    import os
    import sys

    port = 8000
    for idx, arg in enumerate(sys.argv[:-1]):
        if arg in ("--port", "-p"):
            try:
                port = int(sys.argv[idx + 1])
            except ValueError:
                pass
    if "PORT" in os.environ:
        try:
            port = int(os.environ["PORT"])
        except ValueError:
            pass

    if is_port_in_use(port):
        for candidate in [8080, 8081, 8082, 5000, 8888]:
            if not is_port_in_use(candidate):
                print(f"[Notice] Port {port} is occupied by another process. Automatically switching to http://localhost:{candidate}")
                port = candidate
                break

    print(f"Running on http://localhost:{port}")
    uvicorn.run("main:app", host="127.0.0.1", port=port, reload=True)
