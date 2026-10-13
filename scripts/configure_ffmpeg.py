import argparse
import shutil
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--download", action="store_true")
args = parser.parse_args()
ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
if not ffmpeg or not ffprobe:
    if not args.download:
        raise SystemExit("FFmpeg/ffprobe missing. Install through your OS package manager or run with --download.")
    from static_ffmpeg.run import get_or_fetch_platform_executables_else_raise
    ffmpeg, ffprobe = get_or_fetch_platform_executables_else_raise()
path = Path(".env")
if not path.is_file():
    raise SystemExit("Run configure_local.py first")
values = {"FFMPEG": Path(ffmpeg).as_posix(), "FFPROBE": Path(ffprobe).as_posix()}
lines = path.read_text(encoding="utf-8").splitlines()
lines = [line for line in lines if line.split("=", 1)[0].strip() not in values]
lines.extend(key + "=" + value for key, value in values.items())
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("Configured real FFmpeg and ffprobe paths. No model weights were downloaded.")
