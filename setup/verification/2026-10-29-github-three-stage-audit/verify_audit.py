"""Read-only repository consistency and publication scan. Never executes evidence."""
from pathlib import Path
import hashlib
import io
import json
import re
import subprocess
import zipfile
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent

def read(path):
    return (ROOT/path).read_text(encoding="utf-8")

def save(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

def main():
    manifest = json.loads((OUT/"protected-before.json").read_text(encoding="utf-8"))
    changed = [name for name, sha in manifest.items()
               if not (ROOT/name).is_file() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != sha]
    config = json.loads(read("robot/config/robot.json"))
    gate = read("robot/准入关卡.md")
    core = ["README.md", "PLAN.md", "AGENTS.md", "部署说明.md", "robot/README.md",
            "robot/准入关卡.md", "robot/calibration/README.md", "console/README.md",
            "src/wheeltec_explore/README.md", "simulation/README.md", "simulation/regression.md",
            "robot/2026-10-28-实车准入补充.md"]
    broken = []
    for name in core:
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", read(name)):
            if "://" in target or target.startswith("#"):
                continue
            path = unquote(target.split("#")[0])
            if not (ROOT/name).parent.joinpath(path).exists():
                broken.append({"path": name, "target": target})
    historical = ["docs/superpowers/plans/2026-10-27-irregular-frontiers.md",
                  "docs/superpowers/plans/2026-10-28-offline-night.md",
                  "docs/superpowers/specs/2026-10-28-active-scan.md",
                  "simulation/IMPLEMENTATION.md", "simulation/PREPARE.md",
                  "simulation/陌生房间实施计划.md",
                  "setup/automation/g0-night-continuation.md",
                  "setup/automation/irregular-frontiers-continuation.md"]
    numeric = ["robot/calibration/2026-10-27.json", "simulation/config/realism.yaml"]
    unchanged_profiles = all(subprocess.check_output(
        ["git", "hash-object", "--path="+n, n], cwd=ROOT).strip() == subprocess.check_output(
        ["git", "rev-parse", "HEAD:"+n], cwd=ROOT).strip() for n in numeric)
    checks = {
        "exactly_three_real_stages": len(re.findall(r"^## 阶段[一二三]：", gate, re.M)) == 3,
        "no_g6_g9_task_file": not (ROOT/"robot/G1-G9任务清单-草案.md").exists(),
        "hardware_remains_unverified": config["hardware_verified"] is False,
        "approval_remains_null": config["approval_record"] is None,
        "current_approval_protocol": config["admission_protocol"] == "three-stage-20261029",
        "manual_launch_only_first_two_stages": "choices=['1', '2']" in read("robot/launch/manual.launch.py"),
        "full_launch_stage_mapping": "required_gate=3 if explore else 2" in read("robot/launch/robot.launch.py"),
        "adapter_only_three_stages": "choices=[1, 2, 3]" in read("console/target/adapter.py"),
        "watchdog_only_three_stages": "choices=[1,2,3]" in read("robot/watchdog.py").replace(" ", ""),
        "legacy_plans_explicitly_historical": all("历史方案，非现行执行指令" in read(n).splitlines()[0] for n in historical),
        "calibration_profiles_unchanged_in_git": unchanged_profiles,
        "all_protected_evidence_unchanged": not changed,
        "current_local_document_links_resolve": not broken,
        "bounded_odom_check": "15秒" in gate and "不无限重复" in gate,
        "independent_manual_reference": "人工参考地图不是自动真值" in gate and "不得覆盖" in gate,
        "no_unimplemented_test_discovery_stub": not (ROOT/"setup/test_replay_buffer.py").exists(),
    }
    # Scan all publishable files and ZIP text members without printing matched values.
    names = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode().split("\0")
    patterns = {
        "private_key": re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----"),
        "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
        "bearer_literal": re.compile(r"Bearer\s+([A-Za-z0-9_-]{24,})"),
        "credential_literal": re.compile(r"[\"']?(?:password|adapter_token|access_token)[\"']?\s*[:=]\s*[\"']([^\"'\r\n]{12,})", re.I),
    }
    candidates = []
    files_scanned = 0
    def scan(name, data):
        nonlocal files_scanned
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return
        files_scanned += 1
        for label, pattern in patterns.items():
            for match in pattern.finditer(text):
                literal = match.group(0)
                fixture = "NEVER_SAVE_THIS_PASSWORD" in literal and ("console/tests/" in name or "test_transport.py" in name)
                candidates.append({"path": name, "line": text.count("\n", 0, match.start())+1,
                                   "kind": label, "known_test_fixture": fixture})
    for name in sorted(set(names)):
        file = ROOT/name
        if not name or not file.is_file() or file == OUT/"credential-scan.json":
            continue
        data = file.read_bytes()
        if file.suffix == ".zip":
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for member in archive.infolist():
                    if not member.is_dir():
                        scan(name+"!"+member.filename, archive.read(member))
        else:
            scan(name, data)
    blocking = [c for c in candidates if not c["known_test_fixture"]]
    save("credential-scan.json", {"text_files_and_zip_members_scanned": files_scanned,
         "candidate_locations_only": candidates, "blocking_candidates": len(blocking),
         "scope": "Pattern scan plus manual review; no credential values emitted"})
    checks["no_unreviewed_credential_candidates"] = not blocking
    save("checks.json", {"checks": checks, "passed": sum(checks.values()), "total": len(checks),
         "protected_files": len(manifest), "protected_mismatches": changed, "broken_links": broken})
    print(json.dumps({"passed": sum(checks.values()), "total": len(checks), "protected": len(manifest),
                     "broken_links": broken, "credential_candidates": candidates}, ensure_ascii=False))
    return 0 if all(checks.values()) else 1

if __name__ == "__main__":
    raise SystemExit(main())
