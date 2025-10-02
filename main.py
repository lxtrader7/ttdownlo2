from fastapi import FastAPI
from pydantic import BaseModel
import yt_dlp
import uuid
import os
import openai
import subprocess
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import re

# Cargar las variables de entorno
load_dotenv()

# Configurar la API Key de OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

class VideoRequest(BaseModel):
    video_url: str

# --- Utilidades TikTok (solo se usan si hace falta) ---
TT_RE = re.compile(r'https?://(?:www\.)?tiktok\.com/@([^/]+)/(?:video|photo)/(\d+)', re.IGNORECASE)

def is_tiktok_photo(url: str) -> bool:
    return url and "tiktok.com" in url.lower() and "/photo/" in url.lower()

def force_tiktok_video(url: str) -> str:
    m = TT_RE.search(url or "")
    if not m:
        # fallback simple si solo quieres reemplazar la palabra
        return (url or "").replace("/photo/", "/video/")
    user, tt_id = m.group(1), m.group(2)
    return f"https://www.tiktok.com/@{user}/video/{tt_id}"

def has_audio_stream(video_path: str) -> bool:
    try:
        # Usa ffprobe para detectar si hay alguna pista de audio
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-of", "flat", "-show_streams", video_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True
        )
        return "streams.stream[].codec_type=\"audio\"" in result.stdout or "codec_type=\"audio\"" in result.stdout
    except Exception:
        # Si no podemos probar, seguimos e intentamos extraer audio
        return True
# ------------------------------------------------------

@app.post("/process-tiktok")
async def process_tiktok(req: VideoRequest):
    original_url = (req.video_url or "").strip()
    if not original_url:
        return {"error": "Empty URL"}

    video_id = str(uuid.uuid4())
    output_path = f"videos/{video_id}"
    os.makedirs(output_path, exist_ok=True)

    # yt-dlp config (no tocamos nada crítico)
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': f'{output_path}/tiktok.%(ext)s',
        'merge_output_format': 'mp4',
        'noprogress': True,
        # Si tienes temas de región/edad, puedes usar cookies con:
        # 'cookiefile': os.getenv("YT_DLP_COOKIES_FILE")  # ruta a cookies.txt
    }

    def try_download(url: str) -> str:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        # Encontrar archivo de video descargado
        files = os.listdir(output_path)
        video_file = next((f for f in files if f.lower().endswith(('.mp4', '.mkv', '.webm'))), None)
        if not video_file:
            raise RuntimeError("No se encontró el archivo de video descargado.")
        return video_file

    try:
        # 1) Intento directo con la URL original (sea /video/ o /photo/)
        try:
            video_file = try_download(original_url)
            normalized_url_used = original_url
        except Exception as first_err:
            # 2) Solo si es TikTok /photo/ probamos fallback a /video/
            if is_tiktok_photo(original_url):
                fallback_url = force_tiktok_video(original_url)
                video_file = try_download(fallback_url)
                normalized_url_used = fallback_url
            else:
                # No es caso TikTok/photo: propaga el error original
                raise first_err

        video_path = f"{output_path}/{video_file}"

        # Si no hay audio, retornamos info clara sin romper
        if not has_audio_stream(video_path):
            return {
                "video_url": f"https://ttdownlo2.onrender.com/static/{video_id}/{video_file}",
                "no_audio": True,
                "message": "El post no tiene pista de audio (común en algunos TikTok de tipo photo).",
                "normalized_url_used": normalized_url_used
            }

        # Extraer audio con ffmpeg (sobrescribe si existe)
        audio_file_path = f"{output_path}/audio.mp3"
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-acodec", "libmp3lame",
                audio_file_path
            ], check=True)
        except subprocess.CalledProcessError as fferr:
            # Si ffmpeg falla por falta de audio, lo indicamos de forma amable
            return {
                "video_url": f"https://ttdownlo2.onrender.com/static/{video_id}/{video_file}",
                "no_audio": True,
                "message": "No se pudo extraer audio (probablemente el post no tiene pista de audio).",
                "normalized_url_used": normalized_url_used,
                "ffmpeg_error": str(fferr)
            }

        # Transcribir el audio con Whisper
        with open(audio_file_path, "rb") as audio_file:
            transcript = openai.Audio.transcribe(
                model="whisper-1",
                file=audio_file
            )

        return {
            "video_url": f"https://ttdownlo2.onrender.com/static/{video_id}/{video_file}",
            "transcription": transcript.get("text", ""),
            "normalized_url_used": normalized_url_used  # útil para depurar
        }

    except Exception as e:
        return {"error": str(e)}

# Servir archivos estáticos para acceso al video
app.mount("/static", StaticFiles(directory="videos", html=True), name="static")

