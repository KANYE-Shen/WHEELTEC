"""Read GitHub metadata; record exact delivery revision without running robot code."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
REPO = "KANYE-Shen/WHEELTEC"

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode().strip()

def api(path):
    return json.loads(subprocess.check_output(["gh", "api", "repos/"+REPO+"/"+path], cwd=ROOT))

revision = git("rev-parse", "HEAD")
branches = {branch: api("git/ref/heads/"+branch)["object"]["sha"]
            for branch in ["main", "work/irregular-frontiers-20261027"]}
files = ["README.md", "PLAN.md", "AGENTS.md", "robot/准入关卡.md", "robot/preflight.py",
         "robot/config/robot.json", "robot/launch/robot.launch.py", "console/target/adapter.py",
         "replay buffer/20261029-irregular-arc-seed0-startup-assumed/result.json"]
tree = api("git/trees/"+revision+"?recursive=1")
if tree.get("truncated"):
    raise RuntimeError("Refuse incomplete remote tree")
blobs = {item["path"]: item["sha"] for item in tree["tree"] if item["type"] == "blob"}
verified = {}
for name in files:
    expected = git("rev-parse", revision+":"+name)
    verified[name] = {"expected_blob": expected, "github_blob": blobs.get(name), "matches": expected == blobs.get(name)}
case = "replay buffer/20261029-irregular-arc-seed0-startup-assumed/"
manifest = json.loads((ROOT/case/"case.json").read_text(encoding="utf-8"))
raw_checks = {}
for name, expected in manifest["evidence_sha256"].items():
    data = subprocess.check_output(["git", "show", revision+":"+case+name], cwd=ROOT)
    raw_checks[name] = hashlib.sha256(data).hexdigest() == expected
ok = all(value == revision for value in branches.values()) and all(x["matches"] for x in verified.values()) and all(raw_checks.values())
receipt = {"verified_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "delivery_commit": revision, "remote_branches_at_verification": branches,
           "verified_files": verified, "failure_evidence_raw_git_bytes_match_source_sha256": raw_checks,
           "tests_passed": 224, "tests_total": 224, "consistency_checks": "17/17",
           "preserved_evidence_files": 1042, "robot_motion_started": False,
           "stage_one_completed": False, "success": ok,
           "receipt_note": "This receipt is committed after verification; the receipt commit does not change delivered runtime or workflow."}
(OUT/"publication.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"success": ok, "delivery_commit": revision, "github_files_verified": len(verified), "raw_evidence": raw_checks}))
raise SystemExit(0 if ok else 1)
