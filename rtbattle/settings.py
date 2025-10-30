from pathlib import Path
import os, urllib.parse as up, re

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin","django.contrib.auth","django.contrib.contenttypes",
    "django.contrib.sessions","django.contrib.messages","django.contrib.staticfiles",
    "channels",         # 追加
    "arena",            # 追加
]

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "rtbattle.urls"

TEMPLATES = [{
    "BACKEND":"django.template.backends.django.DjangoTemplates",
    "DIRS":[BASE_DIR / "templates"],   # 追加（プロジェクト直下 templates を使う）
    "APP_DIRS":True,
    "OPTIONS":{"context_processors":[
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

ASGI_APPLICATION = "rtbattle.asgi.application"   # Channels用

REDIS_URL = os.getenv("REDIS_URL", "")

def _host_entry(url: str):
    u = up.urlparse(url)
    entry = {
        "address": url,                 # ← URL文字列をそのまま
        "retry_on_timeout": True,
        "socket_timeout": 5,            # 操作のタイムアウト
        "socket_connect_timeout": 5,    # 接続のタイムアウト
        "socket_keepalive": True,       # TCP keepalive
    }
    # rediss:// の時だけTLS系を扱う（まずは厳格。必要なら一時的に緩和）
    if u.scheme == "rediss":
        # entry["ssl_cert_reqs"] = None  # ← 証明書で落ちる時の “一時” 回避（恒久NG）
        pass
    return entry

if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [_host_entry(REDIS_URL)],  # ← dictで渡す
                # "capacity": 1500,   # 必要なら調整
                # "expiry": 10,
            },
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": ["redis://127.0.0.1:6379/0"]},
        }
    }

# 起動ログ（マスク）
def _mask(u: str) -> str:
    return re.sub(r':([^:@/]{6,})@', r':******@', u)
print("[boot] REDIS_URL:", _mask(REDIS_URL or "(empty)"))

# 日本時間にするなら
TIME_ZONE = "Asia/Tokyo"
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
