"""Live acceptance only: no mocked providers, fixture footage or automatic publishing."""
import argparse
import json
import time
from pathlib import Path

import httpx

from xek.config import settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="Start real AI generation after prerequisites pass")
    parser.add_argument("--timeout-hours", type=float, default=8)
    parser.add_argument("--verify-project", help="Verify an existing manually reviewed/rendered project")
    args = parser.parse_args()
    cfg = settings()
    cfg.validate_security()
    api = cfg.public_api_url
    report = {"sample": "XEK — The Weeping Prisoner", "passed": False, "status": "preflight"}
    output = Path("data/acceptance-report.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    def persist():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        with httpx.Client(timeout=60) as client:
            auth = client.post(api + "/auth/login", json={"username": cfg.admin_username, "password": cfg.admin_password})
            auth.raise_for_status()
            client.headers["Authorization"] = "Bearer " + auth.json()["access_token"]
            if args.verify_project:
                response = client.get(api + f"/projects/{args.verify_project}/assets")
                response.raise_for_status()
                assets = response.json()
                movie = next((a for a in assets if a["kind"] == "movie"), None)
                shorts = [a for a in assets if a["kind"] == "short"]
                report.update({"project_id": args.verify_project, "assets": assets,
                               "passed": bool(movie and shorts and movie["metadata"]["quality"]["passed"]),
                               "status": "media-created-needs-human-inspection",
                               "youtube_upload": "Not attempted; requires channel-owner authorization"})
                persist()
                if not report["passed"]:
                    raise RuntimeError("Existing project lacks a quality-passing movie or a rendered Short")
                print("Existing project's real media verified. Human visual/Tamil review remains required.")
                return
            models_response = client.get(api + "/models")
            models_response.raise_for_status()
            models = models_response.json()
            missing = [name for name in ["ollama", "comfyui", "speech"] if not models[name]["reachable"]]
            if missing:
                raise RuntimeError("Required services unavailable: " + ", ".join(missing))
            workflows = models["comfyui"].get("workflows", {})
            if not workflows.get("image", {}).get("configured"):
                raise RuntimeError("Image workflow nodes/models are not ready")
            if not args.run:
                report["status"] = "ready-to-run"
                persist()
                print("Preflight passed; run with --run for actual generation.")
                return
            project = client.post(api + "/projects", json=json.loads(Path("examples/weeping-prisoner.json").read_text(encoding="utf-8")))
            project.raise_for_status()
            project_id = project.json()["id"]
            report["project_id"] = project_id
            deadline = time.monotonic() + args.timeout_hours*3600
            def run_stage(kind):
                queued = client.post(api + f"/projects/{project_id}/jobs", json={"kind": kind})
                queued.raise_for_status()
                job_id = queued.json()["id"]
                last_stage = None
                while time.monotonic() < deadline:
                    response = client.get(api + "/jobs")
                    response.raise_for_status()
                    job = next(j for j in response.json() if j["id"] == job_id)
                    if job["stage"] != last_stage:
                        print(f"{kind}: {job['stage']} ({job['progress']}%)", flush=True)
                        last_stage = job["stage"]
                    if job["state"] == "completed":
                        return
                    if job["state"] in {"failed", "cancelled", "paused"}:
                        raise RuntimeError(f"{kind} {job['state']}: {job.get('error')}")
                    time.sleep(5)
                raise TimeoutError("Acceptance generation timeout; inspect persistent job status")
            run_stage("screenplay")
            response = client.get(api + f"/projects/{project_id}")
            response.raise_for_status()
            project = response.json()
            script = project["screenplay"]
            # No automatic center crops are invented. The operator must confirm focal points.
            if not any(s.get("crop_x") is not None for s in script["shots"]):
                report["status"] = "needs-storyboard-focal-review"
                persist()
                raise RuntimeError("Screenplay created. Confirm at least one shot focal position in Storyboard, "
                                   "approve the script, then render from the UI and run --verify-project")
            approved = client.post(api + f"/projects/{project_id}/approve")
            approved.raise_for_status()
            run_stage("production")
            response = client.get(api + f"/projects/{project_id}/assets")
            response.raise_for_status()
            assets = response.json()
            movie = next((a for a in assets if a["kind"] == "movie"), None)
            shorts = [a for a in assets if a["kind"] == "short"]
            report["assets"] = assets
            report["passed"] = bool(movie and shorts and movie["metadata"]["quality"]["passed"])
            report["status"] = "media-created-needs-human-inspection" if report["passed"] else "acceptance-failed"
            report["youtube_upload"] = "Not attempted; requires channel-owner authorization"
            persist()
            if not report["passed"]:
                raise RuntimeError("Live acceptance requires a quality-passing movie and at least one Short")
            print("Real media generated. Inspect the Tamil movie and Short before publishing or scaling.")
    except Exception as exc:
        report["status"] = "blocked" if report["status"] == "preflight" else report["status"]
        report["error"] = str(exc)[:2000]
        persist()
        raise SystemExit(report["error"]) from None


if __name__ == "__main__":
    main()
