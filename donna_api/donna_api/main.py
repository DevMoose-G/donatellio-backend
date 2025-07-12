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
    allow_origins=[
        "http://localhost:3000",
        "https://donatell.io",
        "https://www.donatell.io",
    ],  # CRA’s default
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# app.add_middleware(
#     CSRFMiddleware,
#     secret="CSRF_SECRET_KEY_CHANGE_ME",  # Change this to a secure random key
#     cookie_secure=True,
#     cookie_samesite="strict",
#     required_urls=[re.compile(r"^/refresh$")],
# )

# Serve all files under ./static at the /static URL path
# app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def health_check():
    """Just a simple health check."""
    return {"status": "OK"}
