from fastapi import FastAPI, File, UploadFile, Form, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional
import subprocess
import random
import os
import shutil
from pathlib import Path
import uuid
import json
from datetime import datetime
from enum import Enum

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = Path("temp_files")
TEMP_DIR.mkdir(exist_ok=True)
JOBS_DIR = Path("jobs")
JOBS_DIR.mkdir(exist_ok=True)

REQUIRED_FONTS = [
    "KOMIKAX_.ttf",
    "Montserrat-Black.ttf",
    "Montserrat-ExtraBold.ttf",
    "Prohibition-RoughOblique.ttf"
]

BACKGROUND_MUSIC_MAP = {
    "1": "tonight.mp3",
    "2": "stranger.mp3",
    "3": "i-was.mp3",
    "4": "suspense.mp3"
}


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


def get_job_file_path(job_id: str) -> Path:
    """Retourne le chemin du fichier JSON du job."""
    return JOBS_DIR / f"{job_id}.json"


def save_job_status(job_id: str, status: JobStatus, progress: int = 0, error: str = None, video_path: str = None):
    """Sauvegarde l'état d'un job dans un fichier JSON."""
    job_data = {
        "job_id": job_id,
        "status": status.value,
        "progress": progress,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "error": error,
        "video_path": video_path
    }

    job_file = get_job_file_path(job_id)
    with open(job_file, 'w', encoding='utf-8') as f:
        json.dump(job_data, f, indent=2)


def get_job_status_data(job_id: str) -> dict:
    """Récupère l'état d'un job depuis le fichier JSON."""
    job_file = get_job_file_path(job_id)

    if not job_file.exists():
        return None

    with open(job_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def copy_fonts_to_workdir(work_dir):
    """Copie les polices nécessaires dans le répertoire de travail."""
    for font in REQUIRED_FONTS:
        font_source = BASE_DIR / font
        if font_source.exists():
            shutil.copy2(font_source, work_dir / font)
            print(f"✅ Police copiée : {font}")
        else:
            print(f"⚠️ Police manquante : {font}")


def get_random_animation(duration, width, height, i, duration_per_image, is_chromatic, is_zoom_pan):
    """Génère une animation aléatoire pour une image avec shake visible et effet chromatique."""

    if is_chromatic == "oui":
        chromatic_effect = (
            f"scale=iw-mod(iw\\,5):ih,"
            f"split=5[v{i}_0][v{i}_1][v{i}_2][v{i}_3][v{i}_4];"
            f"[v{i}_0]crop=iw/5:ih:0*iw/5:0,rgbashift=rh=7:bh=-7:enable='lt(mod(t,0.2),0.1)'[c{i}_0];"
            f"[v{i}_1]crop=iw/5:ih:1*iw/5:0,rgbashift=rh=7:bh=-7:enable='lt(mod(t+0.04,0.2),0.1)'[c{i}_1];"
            f"[v{i}_2]crop=iw/5:ih:2*iw/5:0,rgbashift=rh=7:bh=-7:enable='lt(mod(t+0.08,0.2),0.1)'[c{i}_2];"
            f"[v{i}_3]crop=iw/5:ih:3*iw/5:0,rgbashift=rh=7:bh=-7:enable='lt(mod(t+0.12,0.2),0.1)'[c{i}_3];"
            f"[v{i}_4]crop=iw/5:ih:4*iw/5:0,rgbashift=rh=7:bh=-7:enable='lt(mod(t+0.16,0.2),0.1)'[c{i}_4];"
            f"[c{i}_0][c{i}_1][c{i}_2][c{i}_3][c{i}_4]hstack=inputs=5[v{i}];"
        )
    else:
        chromatic_effect = f"null[v{i}];"

    if is_zoom_pan == "non":
        return (
            f"trim=duration={duration_per_image},"
            f"{chromatic_effect}"
        )
    else:
        animations = [
            f"scale=iw*3:ih*3,"
            f"zoompan=z='zoom+0.002':"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"d={duration}:s={width}x{height},"
            f"trim=duration={duration_per_image},"
            f"{chromatic_effect}",

            f"scale=iw*3:ih*3,"
            f"crop=in_w*0.90:in_h*0.90:(in_w*0.10)/{duration_per_image}*t:108,"
            f"scale={width}:{height},"
            f"trim=duration={duration_per_image},"
            f"{chromatic_effect}",

            f"scale=iw*3:ih*3,"
            f"crop=in_w*0.90:in_h*0.90:"
            f"((in_w - in_w*0.90) / 2):"
            f"in_h*0.10 - (in_h*0.10)/{duration_per_image}*t,"
            f"scale={width}:{height},"
            f"trim=duration={duration_per_image},"
            f"{chromatic_effect}"
        ]

        return random.choice(animations)


def get_audio_duration(file_path):
    """Retourne la durée de l'audio en secondes."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration", "-of",
         "default=noprint_wrappers=1:nokey=1", file_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    return float(result.stdout)


def parse_subtitles(subtitle_string):
    """Parse la chaîne de sous-titres et retourne une liste de mots avec timing."""
    parts = subtitle_string.split('/')
    subtitles = []

    i = 0
    while i < len(parts) - 1:
        subtitles.append({
            'word': parts[i],
            'start': float(parts[i + 1]),
            'end': 0.0
        })
        i += 2

    for i in range(len(subtitles) - 1):
        subtitles[i]['end'] = subtitles[i + 1]['start']

    if subtitles:
        subtitles[-1]['end'] = subtitles[-1]['start'] + 1.0

    return subtitles


def create_ass_file(subtitles, color_stt, color_encours, caption_number, output_file='subtitles.ass'):
    """Crée un fichier ASS à partir des sous-titres parsés."""

    if caption_number == 1:
        style = f"Style: Default,Prohibition Rough,90,{color_stt},&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,9,6,5,10,10,10,1"
    elif caption_number == 2:
        style = f"Style: Default,Montserrat Black,90,{color_stt},&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,11,6,5,10,10,10,1"
    elif caption_number == 3:
        style = f"Style: Default,Komika Axis,110,&H00FFFFFF,{color_stt},&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,7,6,5,10,10,10,1"
    elif caption_number == 4:
        style = f"Style: Default,Montserrat ExtraBold,110,{color_stt},&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,8,6,5,10,10,10,1"
    elif caption_number == 5:
        style = f"Style: Default,Montserrat ExtraBold,90,{color_stt},&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,8,4,5,10,10,10,1"
    elif caption_number == 6:
        style = f"Style: Default,Montserrat ExtraBold,110,{color_stt},&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,7,5,10,10,10,1"
        style_box = f"Style: Box,Montserrat ExtraBold,110,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,3,0,0,5,10,10,10,1"
    elif caption_number == 7:
        style = f"Style: Default,Montserrat ExtraBold,90,{color_stt},&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,8,4,5,10,10,10,1"

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("[Script Info]\n")
        f.write("Title: Auto-generated subtitles\n")
        f.write("ScriptType: v4.00+\n")
        f.write("WrapStyle: 0\n")
        f.write("PlayResX: 1080\n")
        f.write("PlayResY: 1920\n")
        f.write("ScaledBorderAndShadow: yes\n\n")

        f.write("[V4+ Styles]\n")
        f.write(
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")

        f.write(f"{style}\n")
        if caption_number == 6:
            f.write(f"{style_box}\n")
        f.write("\n")

        f.write("[Events]\n")
        f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

        if caption_number == 3 or caption_number == 4 or caption_number == 5 or caption_number == 6:
            i = 0
            while i < len(subtitles):
                group = subtitles[i:i + 3]
                if not group:
                    break

                group = [s for s in group if s['word'] != ' ']
                if not group:
                    i += 3
                    continue

                for j, sub in enumerate(group):
                    word = sub['word']
                    start_time = format_time_ass(group[0]['start'])
                    end_time = format_time_ass(group[-1]['end'])

                    text_parts = []
                    text_parts_box = []

                    for k, s in enumerate(group):
                        if caption_number == 3 or caption_number == 4 or caption_number == 5:
                            w = s['word'].upper()
                        else:
                            w = s['word']
                        if k == j:
                            if caption_number == 3 or caption_number == 4:
                                text_parts.append(f"{{\\blur10\\c{color_encours}&}}{w}{{\\r}}")
                            elif caption_number == 5:
                                text_parts.append(f"{{\\blur10\\t(0,50,\\fs110)\\c{color_encours}&}}{w}{{\\r}}")
                            elif caption_number == 6:
                                text_parts.append(f"{w}")
                                text_parts_box.append(f"{{\\bord7\\3c{color_encours}&\\3a&H00&}}{w}{{\\r}}")
                        else:
                            if caption_number == 3 or caption_number == 4 or caption_number == 5:
                                text_parts.append(f"{{\\blur10}}{w}")
                            elif caption_number == 6:
                                text_parts.append(f"{w}")
                                text_parts_box.append(w)

                    text = " ".join(text_parts)
                    text_box = " ".join(text_parts_box)

                    word_start = format_time_ass(sub['start'])
                    word_end = format_time_ass(sub['end'])

                    if caption_number == 6:
                        f.write(f"Dialogue: 0,{word_start},{word_end},Box,,0,0,0,,{{\\1a&HFF&}}{text_box}\n")
                        f.write(f"Dialogue: 1,{word_start},{word_end},Default,,0,0,0,,{text}\n")
                    else:
                        f.write(f"Dialogue: 0,{word_start},{word_end},Default,,0,0,0,,{text}\n")

                i += 3
        else:
            for sub in subtitles:
                if caption_number == 1:
                    word = sub['word'].upper()
                elif caption_number == 2:
                    word = f"{{\\t(0,100,\\fs110)}}{sub['word']}"
                elif caption_number == 7:
                    word = f"{{\\blur10\\t(0,100,\\fs110)}}{sub['word'].upper()}"

                if word == ' ':
                    continue

                start_time = format_time_ass(sub['start'])
                end_time = format_time_ass(sub['end'])

                f.write(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{word}\n")


def format_time_ass(seconds):
    """Convertit les secondes en format ASS (H:MM:SS.CC)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centisecs = int((seconds % 1) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"


def build_video(images, audio, subtitles_string, image_start_times, caption_number,
                color_stt, color_encours, is_zoom_pan, background_music_path,
                is_chromatic_effect, output_path, work_dir):
    """Génère la vidéo finale avec FFmpeg."""
    WIDTH = 1080
    HEIGHT = 1920
    FPS = 60
    MUSIC_VOLUME = 0.10

    subtitles = parse_subtitles(subtitles_string)
    subtitle_file = os.path.join(work_dir, 'subtitles.ass')
    create_ass_file(subtitles, color_stt, color_encours, caption_number, subtitle_file)

    subtitle_file_ffmpeg = subtitle_file.replace('\\', '/').replace(':', '\\:')
    fonts_dir_ffmpeg = str(work_dir).replace('\\', '/').replace(':', '\\:')

    ffmpeg_cmd = ["ffmpeg", "-y"]

    audio_duration = get_audio_duration(audio)
    image_durations = []

    for i in range(len(images)):
        if i < len(images) - 1:
            duration = image_start_times[i + 1] - image_start_times[i]
        else:
            duration = audio_duration - image_start_times[i]
        image_durations.append(duration)

    for i, img in enumerate(images):
        ffmpeg_cmd += ["-loop", "1", "-t", str(image_durations[i]), "-i", img]

    ffmpeg_cmd += ["-i", audio]

    if background_music_path:
        ffmpeg_cmd += ["-i", background_music_path]

    concat_filter = ""

    for i in range(len(images)):
        duration = image_durations[i]
        frames = int(duration * FPS)
        concat_filter += (
            f"[{i}:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,format=yuv420p,"
        )
        concat_filter += get_random_animation(frames, WIDTH, HEIGHT, i, duration, is_chromatic_effect, is_zoom_pan)

    concat_filter += "".join([f"[v{i}]" for i in range(len(images))])
    concat_filter += f"concat=n={len(images)}:v=1:a=0[vid];"
    concat_filter += f"[vid]ass='{subtitle_file_ffmpeg}':fontsdir='{fonts_dir_ffmpeg}'[outv];"

    if background_music_path:
        concat_filter += f"[{len(images)}:a]volume=1.0[voice];"
        concat_filter += f"[{len(images) + 1}:a]volume={MUSIC_VOLUME}[music];"
        concat_filter += f"[voice][music]amix=inputs=2:duration=shortest[audio_out]"
    else:
        concat_filter += f"[{len(images)}:a]volume=1.0[audio_out]"

    ffmpeg_cmd += [
        "-filter_complex", concat_filter,
        "-map", "[outv]",
        "-map", "[audio_out]",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-shortest",
        output_path
    ]

    subprocess.run(ffmpeg_cmd, check=True)


def process_video_job(job_id: str, image_paths: list, audio_path: str,
                      subtitles_string: str, start_times: list, caption_number_int: int,
                      color_stt: str, color_encours: str, is_zoom_pan: str,
                      background_music_path: Optional[str], is_chromatic_effect: str,
                      work_dir: Path):
    """Traite la génération de vidéo en arrière-plan."""
    try:
        save_job_status(job_id, JobStatus.PROCESSING, progress=10)

        output_path = work_dir / "final_video.mp4"

        copy_fonts_to_workdir(work_dir)
        save_job_status(job_id, JobStatus.PROCESSING, progress=20)

        build_video(
            images=image_paths,
            audio=audio_path,
            subtitles_string=subtitles_string,
            image_start_times=start_times,
            caption_number=caption_number_int,
            color_stt=color_stt,
            color_encours=color_encours,
            is_zoom_pan=is_zoom_pan,
            background_music_path=background_music_path,
            is_chromatic_effect=is_chromatic_effect,
            output_path=str(output_path),
            work_dir=str(work_dir)
        )

        save_job_status(job_id, JobStatus.COMPLETED, progress=100, video_path=str(output_path))

    except Exception as e:
        save_job_status(job_id, JobStatus.FAILED, progress=0, error=str(e))
        print(f"Erreur lors du traitement du job {job_id}: {str(e)}")


@app.post("/generate-video")
async def generate_video(
        background_tasks: BackgroundTasks,
        image1: Optional[UploadFile] = File(None),
        image2: Optional[UploadFile] = File(None),
        image3: Optional[UploadFile] = File(None),
        image4: Optional[UploadFile] = File(None),
        image5: Optional[UploadFile] = File(None),
        image6: Optional[UploadFile] = File(None),
        image7: Optional[UploadFile] = File(None),
        image8: Optional[UploadFile] = File(None),
        image9: Optional[UploadFile] = File(None),
        image10: Optional[UploadFile] = File(None),
        image11: Optional[UploadFile] = File(None),
        image12: Optional[UploadFile] = File(None),
        image13: Optional[UploadFile] = File(None),
        image14: Optional[UploadFile] = File(None),
        image15: Optional[UploadFile] = File(None),
        image16: Optional[UploadFile] = File(None),
        image17: Optional[UploadFile] = File(None),
        image18: Optional[UploadFile] = File(None),
        image19: Optional[UploadFile] = File(None),
        image20: Optional[UploadFile] = File(None),
        image21: Optional[UploadFile] = File(None),
        image22: Optional[UploadFile] = File(None),
        image23: Optional[UploadFile] = File(None),
        image24: Optional[UploadFile] = File(None),
        image25: Optional[UploadFile] = File(None),
        audio: UploadFile = File(...),
        background_music: str = Form(...),
        subtitles_string: str = Form(...),
        image_start_times: str = Form(...),
        caption_number: str = Form(...),
        color_stt: str = Form(...),
        color_encours: str = Form(...),
        is_zoom_pan: str = Form(...),
        is_chromatic_effect: str = Form(...)
):
    """
    Endpoint pour soumettre une génération de vidéo.
    Retourne immédiatement un job_id pour suivre la progression.
    """
    job_id = str(uuid.uuid4())
    work_dir = TEMP_DIR / job_id
    work_dir.mkdir(exist_ok=True)

    try:
        all_images = [
            image1, image2, image3, image4, image5,
            image6, image7, image8, image9, image10,
            image11, image12, image13, image14, image15,
            image16, image17, image18, image19, image20,
            image21, image22, image23, image24, image25
        ]
        uploaded_images = [img for img in all_images if img is not None]

        if not uploaded_images:
            raise ValueError("Aucune image n'a été uploadée")

        image_paths = []
        for i, img in enumerate(uploaded_images):
            img_path = work_dir / f"image_{i}{Path(img.filename).suffix}"
            with open(img_path, "wb") as buffer:
                shutil.copyfileobj(img.file, buffer)
            image_paths.append(str(img_path))

        audio_path = work_dir / f"audio{Path(audio.filename).suffix}"
        with open(audio_path, "wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)

        if background_music == "0":
            background_music_path = None
        else:
            music_filename = BACKGROUND_MUSIC_MAP.get(background_music)
            if not music_filename:
                raise ValueError("Numéro de musique invalide")
            background_music_path = str(BASE_DIR / music_filename)

        caption_number_int = int(caption_number)
        start_times = [float(x.strip()) for x in image_start_times.replace(',', ' ').split() if x.strip()]

        if len(start_times) != len(image_paths):
            if len(start_times) > len(image_paths):
                start_times = start_times[:len(image_paths)]
            else:
                last_time = start_times[-1] if start_times else 0
                while len(start_times) < len(image_paths):
                    last_time += 3.0
                    start_times.append(last_time)

        save_job_status(job_id, JobStatus.PENDING, progress=0)

        background_tasks.add_task(
            process_video_job,
            job_id=job_id,
            image_paths=image_paths,
            audio_path=str(audio_path),
            subtitles_string=subtitles_string,
            start_times=start_times,
            caption_number_int=caption_number_int,
            color_stt=color_stt,
            color_encours=color_encours,
            is_zoom_pan=is_zoom_pan,
            background_music_path=background_music_path,
            is_chromatic_effect=is_chromatic_effect,
            work_dir=work_dir
        )

        return JSONResponse(content={
            "job_id": job_id,
            "status": "pending",
            "message": "Votre vidéo est en cours de génération"
        })

    except Exception as e:
        if work_dir.exists():
            shutil.rmtree(work_dir)
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/job/{job_id}")
async def get_job_status_endpoint(job_id: str):
    """Endpoint pour récupérer l'état d'un job avec l'URL de téléchargement si disponible."""
    job_data = get_job_status_data(job_id)

    if job_data is None:
        raise HTTPException(status_code=404, detail="Job non trouvé")

    # Ajouter l'URL de téléchargement si la vidéo est prête
    if job_data["status"] == JobStatus.COMPLETED.value:
        video_path = job_data.get("video_path")
        if video_path and Path(video_path).exists():
            job_data["video_url"] = f"/job/{job_id}/download"
        else:
            job_data["video_url"] = None
    else:
        job_data["video_url"] = None

    return JSONResponse(content=job_data)


@app.get("/job/{job_id}/download")
async def download_video(job_id: str):
    """Endpoint pour télécharger la vidéo générée une fois le job terminé."""
    job_data = get_job_status_data(job_id)

    if job_data is None:
        raise HTTPException(status_code=404, detail="Job non trouvé")

    if job_data["status"] != JobStatus.COMPLETED.value:
        raise HTTPException(
            status_code=400,
            detail=f"La vidéo n'est pas encore prête. Statut actuel: {job_data['status']}"
        )

    video_path = job_data.get("video_path")

    if not video_path or not Path(video_path).exists():
        raise HTTPException(status_code=404, detail="Fichier vidéo non trouvé")

    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename="generated_video.mp4"
    )


@app.delete("/job/{job_id}")
async def delete_job(job_id: str):
    """Endpoint pour supprimer un job et ses fichiers associés."""
    job_data = get_job_status_data(job_id)

    if job_data is None:
        raise HTTPException(status_code=404, detail="Job non trouvé")

    work_dir = TEMP_DIR / job_id
    if work_dir.exists():
        shutil.rmtree(work_dir)

    job_file = get_job_file_path(job_id)
    if job_file.exists():
        job_file.unlink()

    return JSONResponse(content={"message": "Job supprimé avec succès"})


@app.get("/")
async def root():
    return {
        "message": "API de génération de vidéo avec FFmpeg (version asynchrone)",
        "status": "online",
        "endpoints": {
            "POST /generate-video": "Soumettre une génération de vidéo (retourne un job_id)",
            "GET /job/{job_id}": "Récupérer l'état d'un job avec l'URL de téléchargement si disponible",
            "GET /job/{job_id}/download": "Télécharger la vidéo générée",
            "DELETE /job/{job_id}": "Supprimer un job et ses fichiers"
        }
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)