import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

for key in [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "SOCKS_PROXY",
    "socks_proxy",
]:
    os.environ.pop(key, None)

os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Не найдены SUPABASE_URL или SUPABASE_KEY в файле .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
