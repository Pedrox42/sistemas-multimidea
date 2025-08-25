import subprocess
import threading
import time
import requests

video = "videos/video.mp4"

FFMPEG_PUSH = [
    "ffmpeg", "-re", "-i", video,
    "-c:v", "libx264", "-preset", "veryfast",
    "-maxrate", "3000k", "-bufsize", "6000k",
    "-pix_fmt", "yuv420p", "-g", "12",
    "-c:a", "aac", "-b:a", "128k",
    "-f", "flv", "rtmp://localhost:1935/live/app"
]

def run_ffmpeg(cmd, name):
    try:
        print(f"[FFmpeg-{name}] Starting: {' '.join(cmd)}")
        proc = subprocess.Popen(cmd)

        meta_thread = threading.Thread(target=send_metadata_loop, args=(proc,))
        meta_thread.daemon = True
        meta_thread.start()

        proc.wait()
        print(f"[FFmpeg-{name}] Exited with {proc.returncode}")
    except Exception as e:
        print(f"[FFmpeg-{name}] Error: {e}")

def send_metadata_loop(proc):
    counter = 1
    url = "http://localhost:8080/metadata"

    while proc.poll() is None and counter < 100:
        message = f"message {counter}"
        try:
            requests.post(url, json={"metadata": message, "time": counter})
            print(f"[Metadata] Sent: {message}")
        except Exception as e:
            print(f"[Metadata] Failed to send: {e}")

        counter += 1
        time.sleep(0.5)

if __name__ == "__main__":
    run_ffmpeg(FFMPEG_PUSH, "Push")