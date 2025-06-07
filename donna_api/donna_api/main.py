from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from donna_api.api import router as api_router
from donna_api.auth import router as auth_router
from donna_api.websocket import router as websocket_router

load_dotenv()  # reads .env from cwd

# Initialize FastAPI
app = FastAPI()

app.include_router(websocket_router)
app.include_router(auth_router)
app.include_router(api_router)

# allow local react to interact with backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # CRA’s default
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Serve all files under ./static at the /static URL path
# app.mount("/static", StaticFiles(directory="static"), name="static")
