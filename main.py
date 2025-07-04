from fastapi import FastAPI
from pydantic import BaseModel
import yt_dlp
import uuid
import os
import openai
import subprocess
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# Cargar las variables de entorno
load_dotenv()

# Configurar la API Key de OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

class VideoRequest(BaseModel):
    video_url: str

@app.post("/process-tiktok")
async def process_tiktok(req: VideoRequest):
    video_url = req.video_url
    video_id = str(uuid.uuid4())
    output_path = f"videos/{video_id}"
    os.makedirs(output_path, exist_ok=True)

    try:
        # Descargar el video
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': f'{output_path}/tiktok.%(ext)s',
            'merge_output_format': 'mp4'
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        # Encontrar archivo de video descargado
        files = os.listdir(output_path)
        video_file = next(f for f in files if f.endswith(('.mp4', '.mkv', '.webm')))
        video_path = f"{output_path}/{video_file}"

        # Extraer audio con ffmpeg
        audio_file_path = f"{output_path}/audio.mp3"
        subprocess.run([
            "ffmpeg", "-i", video_path,
            "-vn", "-acodec", "libmp3lame",
            audio_file_path
        ], check=True)

        # Transcribir el audio con Whisper
        with open(audio_file_path, "rb") as audio_file:
            transcript = openai.Audio.transcribe(
                model="whisper-1",
                file=audio_file
            )

        return {
            "video_url": f"https://ttdownlo2.onrender.com/static/{video_id}/{video_file}",
            "transcription": transcript["text"]
        }

    except Exception as e:
        return {"error": str(e)}

# Servir archivos estáticos para acceso al video
app.mount("/static", StaticFiles(directory="videos", html=True), name="static")
