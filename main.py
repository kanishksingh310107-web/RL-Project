# Main entry point to run the app
import uvicorn
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db, get_connection
# A: profile/history integration
from app.db_migrations_a import migrate_a
from app.profile_gate import router as profile_gate_router
# end A: profile/history integration
# B: schedule preferences integration
from app.db_migrations_b import run_b_migration
# Core upgrade: idempotent expense and read-only sharing schema.
from app.db_migrations_core_upgrade import migrate_core_upgrade
from app.db_migrations_d import migrate_d
# end B: schedule preferences integration
from app.api import router
from app.modules import discover, init_module_tables, registry_router

app = FastAPI(title="RL Travel Guide")
# Shared integration: every router uses the same readable API error shape.
from app.errors import install_error_handlers
install_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# A: account/profile routes
app.include_router(profile_gate_router)
# end A: account/profile routes
app.include_router(router)
from app.trip_preview import router as trip_preview_router
app.include_router(trip_preview_router)  # Integration: planning preview and confirmation.
# D: recommendation-led discovery, trip budgeting and assistant APIs.
from app.recommendation_budget import router as recommendation_budget_router
app.include_router(recommendation_budget_router)
# end D: recommendation-led discovery, trip budgeting and assistant APIs.
app.include_router(registry_router)
for _m in discover():
    app.include_router(_m.router)

# C: register the runtime router and its itinerary editing guard.
from app.modules.live import include_c_router
include_c_router(app)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.on_event("startup")
def startup():
    init_db()
    # A: profile/history migration
    migrate_a()
    # end A: profile/history migration
    # B: schedule preferences migration
    run_b_migration()
    # end B: schedule preferences migration
    init_module_tables()
    __import__('app.db_migrations_c', fromlist=['migrate_c']).migrate_c()  # C: runtime schema
    migrate_core_upgrade()
    # D: recommendation/discovery and financial ledger schema.
    with get_connection() as conn:
        migrate_d(conn)
    # end D: recommendation/discovery and financial ledger schema.

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
