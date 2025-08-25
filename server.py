import os
import subprocess
import threading
import time
from pathlib import Path

from flask import Flask, send_from_directory, jsonify, request, render_template
import xml.etree.ElementTree as ET

app = Flask(__name__)

DASH_DIR = os.path.join("live", "app")
HTTP_PORT = 8080
ffmpeg_dash_proc = None
metadata_array = []

FFMPEG_DASH = [
    "ffmpeg", "-listen", "1", "-i", "rtmp://localhost:1935/live/app",
    "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency", "-g", "12",
    "-c:a", "aac", "-ar", "48000", "-b:a", "96k",
    "-keyint_min", "30", "-sc_threshold", "0",
    "-use_template", "1", "-use_timeline", "1",
    "-window_size", "5", "-extra_window_size", "10",
    "-streaming", "1", "-seg_duration", "2", "-frag_duration", "1",
    "-f", "dash", "-live", "1", os.path.join(DASH_DIR, "manifest.mpd")
]

@app.route('/live/app/<path:filename>')
def serve_dash(filename):
    return send_from_directory(DASH_DIR, filename)

@app.route('/stream_alive')
def stream_alive():
    alive = ffmpeg_dash_proc and ffmpeg_dash_proc.poll() is None
    return {"alive": alive}

@app.route('/metadata', methods=["POST"])
def receive_metadata():
    data = request.get_json(force=True)
    message = data.get("metadata", "")
    if message:
        metadata_array.append(data)
        print(f"[Metadata] Received: {message}")
    return jsonify({"status": "ok", "received": message})

@app.route('/metadata_feed')
def metadata_feed():
    return jsonify({"messages": metadata_array})

@app.route('/watch')
def watch_page():
    return render_template("live.html")

def clean(path):
    dir_path = Path(path)
    if not dir_path.is_dir():
        raise NotADirectoryError(f"{path}: directory not found")

    for item in dir_path.iterdir():
        if item.name == ".gitkeep":
            continue
        if item.is_file():
            item.unlink()

def run_ffmpeg(cmd, name):
    global ffmpeg_dash_proc

    clean("live/app")

    try:
        print(f"[FFmpeg-{name}] Starting: {' '.join(cmd)}")
        proc = subprocess.Popen(cmd)
        if name == "DASH":
            ffmpeg_dash_proc = proc
        proc.wait()
        print(f"[FFmpeg-{name}] Exited with {proc.returncode}")
    except Exception as e:
        print(f"[FFmpeg-{name}] Error: {e}")

def wait_for_manifest():
    manifest_path = os.path.join(DASH_DIR, "manifest.mpd")
    while not os.path.exists(manifest_path) or os.path.getsize(manifest_path) == 0:
        time.sleep(0.1)
    print("[Server] First manifest ready, clients can now connect.")

def write_live_manifest(mpd_path, ns, persistent_events, live_mpd_path, metadata_index):
    increment_metadata_index = False
    try:
        if not os.path.exists(mpd_path) or os.path.getsize(mpd_path) == 0:
            return False

        tree = ET.parse(mpd_path)
        root = tree.getroot()

        period = root.find("mpd:Period", ns)
        if period is None:
            return False

        event_stream = ET.Element("{%s}EventStream" % ns["mpd"], {
            "schemeIdUri": "urn:metadata",
            "timescale": "1",
            "value": "metadata"
        })

        for idx, ev in enumerate(persistent_events):
            ET.SubElement(event_stream, "{%s}Event" % ns["mpd"], {
                "presentationTime": str(ev["presentationTime"]),
                "duration": str(ev["duration"]),
                "id": str(idx)
            }).text = ev["text"]

        if len(metadata_array) > metadata_index:
            msg = metadata_array[metadata_index]["metadata"]
            presentation_time = int(metadata_array[metadata_index]["time"])
            duration = 1
            ev = {
                "presentationTime": presentation_time,
                "duration": duration,
                "text": msg
            }
            persistent_events.append(ev)

            ET.SubElement(event_stream, "{%s}Event" % ns["mpd"], {
                "presentationTime": str(presentation_time),
                "duration": str(duration),
                "id": str(len(persistent_events) - 1)
            }).text = msg

            print(f"[MPD] Added event: {msg}")

            for old_es in period.findall("mpd:EventStream", ns):
                period.remove(old_es)

            increment_metadata_index = True

        period.append(event_stream)

        tree.write(live_mpd_path, encoding="utf-8", xml_declaration=True)
        return increment_metadata_index
    except Exception as e:
        print("[MPD] Error updating live-manifest.mpd:", e)

def update_live_manifest():
    ns = {"mpd": "urn:mpeg:dash:schema:mpd:2011"}
    ET.register_namespace("", ns["mpd"])

    live_mpd_path = os.path.join(DASH_DIR, "live-manifest.mpd")
    mpd_path = os.path.join(DASH_DIR, "manifest.mpd")

    persistent_events = []
    metadata_index = 0
    while True:
        if write_live_manifest(mpd_path, ns, persistent_events, live_mpd_path, metadata_index):
            metadata_index += 1
        else:
            time.sleep(0.2)

        if ffmpeg_dash_proc and ffmpeg_dash_proc.poll() is not None:
            break

        time.sleep(0.2)
    write_live_manifest(mpd_path, ns, persistent_events, live_mpd_path, metadata_index)


if __name__ == "__main__":
    os.makedirs(DASH_DIR, exist_ok=True)

    threading.Thread(target=run_ffmpeg, args=(FFMPEG_DASH, "DASH"), daemon=True).start()
    threading.Thread(target=wait_for_manifest, daemon=True).start()
    threading.Thread(target=update_live_manifest, daemon=True).start()

    app.run(host="0.0.0.0", port=HTTP_PORT, debug=False, use_reloader=False)