import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = ["corsheaders", "routing"]
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
]

# In production Django also serves the built React app (frontend/dist), so one service hosts everything.
_DIST = BASE_DIR.parent / "frontend" / "dist"
if _DIST.is_dir():  # absent on Vercel, where the CDN serves the React app
    WHITENOISE_ROOT = _DIST
    WHITENOISE_INDEX_FILE = True
STATIC_URL = "/static/"
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# The app is stateless: every plan is computed from live routing and weather APIs.
DATABASES = {}
CORS_ALLOW_ALL_ORIGINS = True

USE_TZ = True
TIME_ZONE = "UTC"
