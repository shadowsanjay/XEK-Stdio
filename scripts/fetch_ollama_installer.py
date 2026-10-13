"""Download the official Windows installer with a verified GitHub release digest."""
import argparse
import hashlib
import shutil
from pathlib import Path

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--version", default="latest")
args = parser.parse_args()
release = "latest" if args.version == "latest" else "tags/" + args.version
metadata = httpx.get("https://api.github.com/repos/ollama/ollama/releases/" + release, timeout=30)
metadata.raise_for_status()
asset = next(a for a in metadata.json()["assets"] if a["name"] == "OllamaSetup.exe")
digest = asset.get("digest", "")
if not digest.startswith("sha256:"):
    raise SystemExit("Release has no SHA256 digest; use the normal official Windows installer")
folder = Path(".runtime/installers")
folder.mkdir(parents=True, exist_ok=True)
if shutil.disk_usage(folder).free < asset["size"] * 2 + 8 * 1024**3:
    raise SystemExit("Insufficient disk headroom for installer and extracted application")
partial, output = folder / "OllamaSetup.exe.part", folder / "OllamaSetup.exe"
if not output.exists():
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    with httpx.stream("GET", asset["browser_download_url"], headers=headers,
                      follow_redirects=True, timeout=30) as response:
        response.raise_for_status()
        append = response.status_code == 206
        downloaded = offset if append else 0
        announced = downloaded
        with partial.open("ab" if append else "wb") as file:
            for chunk in response.iter_bytes(1024 * 1024):
                file.write(chunk)
                downloaded += len(chunk)
                if downloaded - announced >= 100 * 1024**2:
                    print(f"Installer downloaded: {downloaded/1024**2:.0f}/{asset['size']/1024**2:.0f} MiB", flush=True)
                    announced = downloaded
    if partial.stat().st_size != asset["size"]:
        raise SystemExit("Installer download incomplete; rerun to resume")
    partial.replace(output)
hasher = hashlib.sha256()
with output.open("rb") as file:
    for chunk in iter(lambda: file.read(1024 * 1024), b""):
        hasher.update(chunk)
if hasher.hexdigest() != digest.split(":", 1)[1]:
    raise SystemExit("Installer SHA256 mismatch: do not execute it")
print(f"Verified official Ollama installer {metadata.json()['tag_name']}: {output.resolve()}")
