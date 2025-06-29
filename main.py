from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import yt_dlp
import uuid
import os

app = FastAPI()

# Modelo para solicitudes POST
class VideoRequest(BaseModel):
    video_url: str

# Endpoint principal para solicitudes POST
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
            "video_url": f"https://ttdownlo2.onrender.com/static/{video_id}/{video_file}"
        }

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

# Montar carpeta 'videos' como archivos estáticos
app.mount("/static", StaticFiles(directory="videos", html=True), name="static")

# (Opcional) Ruta GET para pruebas rápidas vía navegador
@app.get("/")
async def handle_get_url(url: str):
    return await process_tiktok(VideoRequest(video_url=url))
