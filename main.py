from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import auth, users, assets, tests, board

app = FastAPI(title="Pentest Planner API - PRO")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Wire up all the separated routes!
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(assets.router)
app.include_router(tests.router)
app.include_router(board.router)