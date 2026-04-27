import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    raise ValueError("Не найдены SUPABASE_URL или SUPABASE_SECRET_KEY в файле .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
