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
        # fallback simple si solo quieres reemplazar la palabra (no rompe otros dominios)
        return (url or "").replace("/photo/", "/video/")
    user, tt_id = m.group(1), m.group(2)
    return f"https://www.tiktok.com/@{user}/video/{tt_id}"
# ------------------------------------------------------

@app.post("/process-tiktok")
async def process_tiktok(req: VideoRequest):
    original_url = (req.video_url or "").strip()
    if not original_url:
        return {"error": "Empty URL"}

    video_id = str(uuid.uuid4())
    output_path = f"videos/{video_id}"
    os.makedirs(output_path, exist_ok=True)

    # Config general para video
    ydl_opts_video = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': f'{output_path}/tiktok.%(ext)s',
        'merge_output_format': 'mp4',
        'noprogress': True,
    }

    def try_download_video(url: str) -> str | None:
        """Intenta descargar un contenedor de video. Retorna filename o None si no hay video."""
        with yt_dlp.YoutubeDL(ydl_opts_video) as ydl:
            ydl.download([url])
        files = os.listdir(output_path)
        return next((f for f in files if f.lower().endswith(('.mp4', '.mkv', '.webm'))), None)

    # Config para audio-only (fallback para slideshow)
    ydl_opts_audio = {
        'format': 'bestaudio/best',
        'outtmpl': f'{output_path}/audio.%(ext)s',
        'noprogress': True,
        # Extrae directo a MP3 (evita tu paso de ffmpeg aparte cuando no hay video)
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192'
        }]
    }

    def try_download_audio(url: str) -> str | None:
        """Descarga solo el audio y lo deja como MP3. Retorna path del mp3 o None."""
        with yt_dlp.YoutubeDL(ydl_opts_audio) as ydl:
            ydl.download([url])
        files = os.listdir(output_path)
        mp3 = next((f for f in files if f.lower().endswith('.mp3')), None)
        return f"{output_path}/{mp3}" if mp3 else None

    try:
        # 1) Intento directo con la URL original (sea /video/ o /photo/)
        normalized_url_used = original_url
        video_file = None

        try:
            video_file = try_download_video(normalized_url_used)
        except Exception as first_err:
            # 2) Si es TikTok/photo, intento fallback cambiando a /video/
            if is_tiktok_photo(original_url):
                normalized_url_used = force_tiktok_video(original_url)
                video_file = try_download_video(normalized_url_used)
            else:
                raise first_err

        audio_file_path = None

        if video_file:
            # Si sí hay video, extrae audio con ffmpeg (tu flujo original)
            video_path = f"{output_path}/{video_file}"
            audio_file_path = f"{output_path}/audio.mp3"
            subprocess.run([
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-acodec", "libmp3lame",
                audio_file_path
            ], check=True)
        else:
            # 3) No hay contenedor de video (común en TikTok photo) → baja solo el audio
            audio_file_path = try_download_audio(normalized_url_used)
            if not audio_file_path and is_tiktok_photo(original_url) and normalized_url_used == original_url:
                # último intento: si aún no hicimos el fallback, forzamos /video/ y probamos audio
                normalized_url_used = force_tiktok_video(original_url)
                audio_file_path = try_download_audio(normalized_url_used)

            if not audio_file_path:
                return {"error": "No se encontró el archivo de video y no se pudo obtener el audio."}

        # 4) Transcribir el audio con Whisper
        with open(audio_file_path, "rb") as audio_file:
            transcript = openai.Audio.transcribe(
                model="whisper-1",
                file=audio_file
            )

        # 5) Armar respuesta
        resp = {
            "transcription": transcript.get("text", ""),
            "normalized_url_used": normalized_url_used  # útil para debug
        }
        # Expón el video si existe
        if video_file:
            resp["video_url"] = f"https://ttdownlo2.onrender.com/static/{video_id}/{video_file}"
        else:
            # deja un link al folder por si quieres inspeccionar el MP3
            resp["audio_only"] = True

        return resp

    except Exception as e:
        return {"error": str(e)}

# Servir archivos estáticos para acceso al video
app.mount("/static", StaticFiles(directory="videos", html=True), name="static")

