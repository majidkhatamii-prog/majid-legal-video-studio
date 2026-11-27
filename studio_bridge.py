#!/usr/bin/env python3
# Local-only bridge between the Legal Video Studio (GitHub Pages) and Sedabot.
# Place this file beside Sedabot's cli.py, then run start_studio_bridge.bat.
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import re

ROOT = Path(__file__).resolve().parent
CLI = ROOT / "cli.py"
PORT = 8765
ALLOWED_ORIGINS = {
    "https://majidkhatamii-prog.github.io",
    "http://127.0.0.1:8765",
    "http://localhost:8765",
}
VOICE_RE = re.compile(r"^fa_IR-[a-z0-9_]+-medium$")

def run_cli(args, timeout=180):
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

def installed_voices():
    result = run_cli(["--list-voices"], timeout=45)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "Sedabot CLI failed")[-1200:])
    voices = []
    for line in result.stdout.splitlines():
        parts = line.strip().split("\t")
        if len(parts) >= 3 and parts[1].strip().lower() == "installed":
            voice_id = parts[0].strip()
            if VOICE_RE.fullmatch(voice_id):
                voices.append({"id": voice_id, "title": parts[2].strip()})
    return voices

class Handler(BaseHTTPRequestHandler):
    server_version = "MajidLegalStudioBridge/1.0"

    def log_message(self, fmt, *args):
        print("[Studio Bridge] " + (fmt % args))

    def cors(self):
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            if self.headers.get("Access-Control-Request-Private-Network") == "true":
                self.send_header("Access-Control-Allow-Private-Network", "true")

    def send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        origin = self.headers.get("Origin", "")
        if origin not in ALLOWED_ORIGINS:
            self.send_error(403, "Origin not allowed")
            return
        self.send_response(204)
        self.cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.headers.get("Origin", "") not in ALLOWED_ORIGINS:
            self.send_error(403, "Open the studio from its official GitHub Pages address.")
            return
        if self.path not in ("/health", "/voices"):
            self.send_error(404)
            return
        try:
            voices = installed_voices()
            self.send_json(200, {
                "ok": True,
                "app": "Sedabot",
                "voices": voices,
                "message": "اتصال به Sedabot برقرار است."
            })
        except Exception as exc:
            self.send_json(500, {"ok": False, "error": str(exc)})

    def do_POST(self):
        if self.headers.get("Origin", "") not in ALLOWED_ORIGINS:
            self.send_error(403, "Origin not allowed")
            return
        if self.path != "/synthesize":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 1_000_000:
                self.send_json(413, {"error": "متن خالی یا بیش از حد طولانی است."})
                return
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            text = str(body.get("text", "")).strip()
            voice = str(body.get("voice", "fa_IR-gyro-medium")).strip()
            speed = float(body.get("speed", 1.2))
            if not text:
                self.send_json(400, {"error": "متن گویندگی خالی است."})
                return
            if len(text) > 50000:
                self.send_json(413, {"error": "متن بیش از ۵۰ هزار نویسه است."})
                return
            if not VOICE_RE.fullmatch(voice):
                self.send_json(400, {"error": "شناسه مدل صدا معتبر نیست."})
                return
            if not 0.65 <= speed <= 1.60:
                self.send_json(400, {"error": "سرعت باید بین ۰٫۶۵ تا ۱٫۶ باشد."})
                return
            available = {v["id"] for v in installed_voices()}
            if voice not in available:
                self.send_json(400, {"error": "این مدل صدا در پوشه Sedabot نصب نیست."})
                return
            with tempfile.TemporaryDirectory(prefix="majid-tts-") as temp:
                temp_dir = Path(temp)
                text_path = temp_dir / "script.txt"
                wav_path = temp_dir / "narration.wav"
                text_path.write_text(text, encoding="utf-8")
                result = run_cli([
                    "--voice", voice,
                    "--speed", str(speed),
                    "--text-file", str(text_path),
                    "--out", str(wav_path),
                    "--no-play",
                ], timeout=240)
                if result.returncode != 0 or not wav_path.exists():
                    detail = (result.stderr or result.stdout or "فایل صوتی ساخته نشد.")[-1600:]
                    self.send_json(500, {"error": detail})
                    return
                audio = wav_path.read_bytes()
            self.send_response(200)
            self.cors()
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(audio)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(audio)
        except subprocess.TimeoutExpired:
            self.send_json(504, {"error": "ساخت گویندگی بیش از زمان مجاز طول کشید."})
        except Exception as exc:
            self.send_json(500, {"error": str(exc)})

if __name__ == "__main__":
    if not CLI.exists():
        print("خطا: فایل cli.py پیدا نشد. این فایل باید کنار cli.py در پوشه Sedabot باشد.")
        input("برای خروج یک کلید بزنید...")
        raise SystemExit(1)
    print("اتصال محلی استودیوی ویدئو آماده است.")
    print("این پنجره را باز نگه دارید؛ سپس در استودیو روی «اتصال به موتور فارسی» بزنید.")
    print("آدرس محلی: http://127.0.0.1:8765")
    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except OSError as exc:
        print("پورت 8765 در دسترس نیست:", exc)
        input("برای خروج یک کلید بزنید...")
