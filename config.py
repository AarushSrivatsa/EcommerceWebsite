from dotenv import load_dotenv
import os

load_dotenv()

GROQ_API_KEY = os.getenv('GROQ_API_KEY')
DATABASE_URL = os.getenv('DATABASE_URL')
OUTPUT_DIR = os.getenv('OUTPUT_DIR', 'output')          # scratch space for renders (temp files only)

# Supabase storage (use the service_role key, this runs on the server only)
SUPABASE_URL = (os.getenv('SUPABASE_URL') or '').rstrip('/')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')
IMAGES_BUCKET = os.getenv('IMAGES_BUCKET', 'images')
VIDEOS_BUCKET = os.getenv('VIDEOS_BUCKET', 'videos')
AUDIOS_BUCKET = os.getenv('AUDIOS_BUCKET', 'audios')
SUPABASE_BUCKETS_PUBLIC = os.getenv('SUPABASE_BUCKETS_PUBLIC', 'true').lower() == 'true'   # false -> signed urls
SIGNED_URL_SECONDS = int(os.getenv('SIGNED_URL_SECONDS', '3600'))
