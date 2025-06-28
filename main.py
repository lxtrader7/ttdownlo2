from fastapi import FastAPI
from pydantic import BaseModel
import yt_dlp
import uuid
import os

app = FastAPI()

class VideoRequest(BaseModel):
    video_url: str

@app.post("/process-tiktok")
async def process_tiktok(req: VideoRequest):
    video_url = req.video_url
    video_id = str(uuid.uuid4())
    output_path = f"videos/{video_id}"

    os.makedirs(output_path, exist_ok=True)

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': f'{output_path}/tiktok.%(ext)s',
        'merge_output_format': 'mp4'
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        # Buscar el archivo descargado
        files = os.listdir(output_path)
        video_file = next(f for f in files if f.endswith(('.mp4', '.mkv', '.webm')))
        video_path = f"{output_path}/{video_file}"

        return {
            "video_url": f"https://yourapp.onrender.com/static/{video_id}/{video_file}"
        }
    except Exception as e:
        return {"error": str(e)}

# Archivos estáticos para acceso al video
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="videos", html=True), name="static")
