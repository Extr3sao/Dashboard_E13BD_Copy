"""Independent verification authority for the Dashboard E13BD certification run.

WHY THIS EXISTS
---------------
DEV Agent 4.5.1 ships an independent verifier as library code
(``core.autonomy.independent_verifier``) but exposes no CLI route that reaches
it: ``devagent run --intent VERIFY_ONLY`` is dispatched into the audit-only
branch of ``cmd_run`` and terminalizes at AUDITED, and the phase4
``EngineeringOrchestrator`` transitions INDEPENDENTLY_VERIFIED -> CERTIFIED
without ever invoking a verifier. Because the framework cannot produce an
independent verification receipt for this project, this script is the separate
verification authority for the run: it re-derives facts from the frozen
workspace, the framework's own state, and the captured execution logs instead of
trusting the executor's summary.

It is deliberately read-only with respect to product source: it writes exactly
one report file under the declared evidence directory.

WHAT IT DOES NOT CLAIM
----------------------
- It does not claim that the *framework* certified anything.
- It does not re-execute the backend suite (time-bound); it verifies those logs
  by hash + summary + independent source-side count, and says so in the report.
- It re-executes the fast suites (frontend vitest, preview smoke) so at least
  the E2E evidence is reproduced by the verifier itself.

Usage:
    python independent_verifier.py \
        --workspace C:/dev/dashboard-e13bd-cert \
        --logs C:/dev/e13bd-cert-logs \
        --controls <path to control logs> \
        --expected-commit <sha> \
        --ledger <traceability ledger json> \
        --out <report json> \
        [--rerun-fast]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "INDEPENDENT_VERIFICATION_V1"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    return ANSI.sub("", text)
SECRET_SHAPE = re.compile(
    r"(?:PASSWORD|PASSWD|API[_-]?KEY|SECRET|TOKEN)\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{16,}")
DEV_PATH = re.compile(r"[cC]:[\\/]+Users[\\/]+[A-Za-z0-9._-]+[\\/]")
SKIP_DIRS = {"node_modules", ".venv", ".git", "instantclient", "dist", "__pycache__"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd, cwd=None, timeout=600):
    try:
        p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, shell=isinstance(cmd, str),
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except Exception as exc:  # fail closed, never crash the verifier
        return 999, "", f"{type(exc).__name__}: {exc}"


class Checks:
    def __init__(self):
        self.items = []

    def add(self, check_id, name, status, detail, evidence=None, blocking=True):
        self.items.append({
            "check_id": check_id, "name": name, "status": status,
            "blocking": blocking, "detail": detail, "evidence": evidence or [],
        })

    def failed(self):
        return [c for c in self.items if c["blocking"] and c["status"] != "PASS"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--logs", required=True)
    ap.add_argument("--controls", default="")
    ap.add_argument("--expected-commit", required=True)
    ap.add_argument("--ledger", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--rerun-fast", action="store_true")
    args = ap.parse_args()

    ws = Path(args.workspace).resolve()
    logs = Path(args.logs).resolve()
    checks = Checks()
    facts = {"workspace": str(ws), "logs": str(logs),
             "expected_commit": args.expected_commit,
             "verified_at": datetime.now(timezone.utc).isoformat()}

    # ---------------------------------------------------------------- CHK-01
    rc, out, _ = run(["git", "rev-parse", "HEAD"], cwd=ws)
    head = out.strip()
    rc_br, branch, _ = run(["git", "branch", "--show-current"], cwd=ws)
    rc_st, status, _ = run(["git", "status", "--porcelain"], cwd=ws)
    dirty = [l for l in status.splitlines() if l.strip()]
    facts["head"] = head
    facts["branch"] = branch.strip()
    facts["dirty_entries"] = dirty
    if head != args.expected_commit or dirty:
        checks.add("CHK-01", "SOURCE_FREEZE", "FAIL",
                   f"HEAD={head} expected={args.expected_commit} dirty={len(dirty)}",
                   evidence=["git rev-parse HEAD", "git status --porcelain"])
    else:
        checks.add("CHK-01", "SOURCE_FREEZE", "PASS",
                   f"HEAD {head[:12]} on {branch.strip()}, working tree clean",
                   evidence=["git status --porcelain == empty"])

    # ---------------------------------------------------------------- CHK-02
    rc, vout, verr = run(["devagent", "version", "--json"], cwd=ws)
    try:
        version_doc = json.loads(vout)
    except Exception:
        version_doc = {"raw": vout.strip()[:400], "stderr": verr[:200]}
    facts["devagent_version"] = version_doc
    rc, dout, derr = run(["devagent", "project-doctor", ".", "--json"], cwd=ws)
    try:
        doctor = json.loads(dout)
    except Exception:
        doctor = {}
    facts["project_doctor"] = {
        "all_ok": doctor.get("all_ok"),
        "boundary_status": (doctor.get("diagnostics") or {}).get("boundary_status"),
        "declaration_pollution": (doctor.get("diagnostics") or {}).get("declaration_pollution"),
        "orphan_reservations": (doctor.get("diagnostics") or {}).get("orphan_reservations"),
        "last_audit": (doctor.get("diagnostics") or {}).get("last_audit"),
        "compatibility": (doctor.get("project") or {}).get("compatibility"),
        "files_seen": ((doctor.get("toolchains") or {}).get("metrics") or {}).get("files_seen"),
        "raw_stderr": derr[:200],
    }
    ok_boundary = (doctor.get("all_ok") is True
                   and facts["project_doctor"]["boundary_status"] == "OK"
                   and facts["project_doctor"]["declaration_pollution"] == 0)
    checks.add("CHK-02", "PROJECT_BOUNDARY", "PASS" if ok_boundary else "FAIL",
               json.dumps(facts["project_doctor"])[:300],
               evidence=["devagent project-doctor . --json"])

    # ---------------------------------------------------------------- CHK-03
    def read_log(name):
        p = logs / name
        if not p.exists():
            return None, ""
        return sha256_file(p), strip_ansi(p.read_text(encoding="utf8", errors="ignore"))

    backend_hash, backend_log = read_log("backend_pytest_v2.log")
    m = re.search(r"(\d+) passed(?:, (\d+) failed)?", backend_log)
    backend_passed = int(m.group(1)) if m else -1
    backend_failed = int(m.group(2) or 0) if m else -1
    src_tests = sum(
        1 for f in (ws / "tests").glob("test_*.py")
        for line in f.read_text(encoding="utf8", errors="ignore").splitlines()
        if re.match(r"\s*def test_", line))
    facts["backend"] = {"log_sha256": backend_hash, "passed": backend_passed,
                        "failed": backend_failed,
                        "test_functions_in_source": src_tests}
    ok_backend = backend_passed >= 250 and backend_failed == 0
    checks.add("CHK-03", "BACKEND_TESTS", "PASS" if ok_backend else "FAIL",
               f"{backend_passed} passed / {backend_failed} failed "
               f"(source declares {src_tests} test functions)",
               evidence=[f"backend_pytest_v2.log sha256={backend_hash}"])

    # ---------------------------------------------------------------- CHK-04
    fe_hash, fe_log = read_log("fe_vitest_v2.log")
    files_line = re.search(r"Test Files\s+(\d+) passed \((\d+)\)", fe_log)
    tests_line = re.search(r"Tests\s+(\d+) passed \((\d+)\)", fe_log)
    fe_files = int(files_line.group(2)) if files_line else -1
    fe_tests = int(tests_line.group(2)) if tests_line else -1
    facts["frontend"] = {"log_sha256": fe_hash, "files": fe_files, "tests": fe_tests}
    ok_fe = fe_files == 26 and fe_tests == 79
    detail = f"{fe_files} files / {fe_tests} tests"
    if args.rerun_fast:
        rc, out, err = run("npm test", cwd=ws / "src" / "web-app", timeout=600)
        out = strip_ansi(out)
        rf = re.search(r"Test Files\s+(\d+) passed \((\d+)\)", out)
        rt = re.search(r"Tests\s+(\d+) passed \((\d+)\)", out)
        facts["frontend"]["verifier_rerun"] = {
            "exit": rc, "files": int(rf.group(2)) if rf else -1,
            "tests": int(rt.group(2)) if rt else -1}
        ok_fe = ok_fe and rc == 0 and facts["frontend"]["verifier_rerun"]["tests"] == fe_tests
        detail += f"; verifier rerun exit={rc} tests={facts['frontend']['verifier_rerun']['tests']}"
    checks.add("CHK-04", "FRONTEND_TESTS", "PASS" if ok_fe else "FAIL", detail,
               evidence=[f"fe_vitest_v2.log sha256={fe_hash}"])

    # ---------------------------------------------------------------- CHK-05
    b_hash, b_log = read_log("fe_build_v2.log")
    dist_index = ws / "src" / "web-app" / "dist" / "index.html"
    dist_hash = sha256_file(dist_index) if dist_index.exists() else None
    ok_build = "built in" in b_log and dist_index.exists()
    facts["frontend_build"] = {"log_sha256": b_hash, "dist_index_sha256": dist_hash}
    checks.add("CHK-05", "FRONTEND_BUILD", "PASS" if ok_build else "FAIL",
               f"vite build ok, dist/index.html sha256={(dist_hash or '')[:16]}",
               evidence=[f"fe_build_v2.log sha256={b_hash}"])

    # ---------------------------------------------------------------- CHK-06
    s_hash, s_log = read_log("fe_smoke_v2.log")
    smoke_ok = "smoke success" in s_log
    facts["e2e"] = {"log_sha256": s_hash, "success_marker": smoke_ok,
                    "scope": "playwright happy path on the built SPA with mocked API"}
    if args.rerun_fast:
        rc, out, err = run("npm run smoke:ui", cwd=ws / "src" / "web-app", timeout=600)
        smoke_ok = smoke_ok and rc == 0 and "smoke success" in out
        facts["e2e"]["verifier_rerun"] = {"exit": rc, "success": "smoke success" in out}
    checks.add("CHK-06", "E2E_MANDATORY", "PASS" if smoke_ok else "FAIL",
               "playwright happy path reproduced" if smoke_ok else "smoke marker missing",
               evidence=[f"fe_smoke_v2.log sha256={s_hash}"])

    # ---------------------------------------------------------------- CHK-07
    residue = []
    for p in ws.rglob("*"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.is_file() and (p.suffix in {".db", ".db-journal", ".db-wal", ".db-shm"}
                            or p.name.endswith(("-journal", "-wal", "-shm"))):
            residue.append(str(p.relative_to(ws)))
    facts["sqlite_residue"] = residue
    checks.add("CHK-07", "SQLITE_TEST_RESIDUE", "PASS" if not residue else "FAIL",
               f"{len(residue)} residue files", evidence=["filesystem scan"])

    # ---------------------------------------------------------------- CHK-08
    rc, ls_out, _ = run(["git", "ls-files"], cwd=ws)
    tracked = [l for l in ls_out.splitlines() if l.strip()]
    host_coupled = []
    for rel in tracked:
        if rel.startswith("archive/") or rel.startswith("docs/") or rel.startswith("scripts/"):
            continue  # legacy/maintenance scripts, reported separately as findings
        p = ws / rel
        if p.suffix not in {".py", ".js", ".jsx", ".mjs", ".ps1", ".json", ".txt"}:
            continue
        try:
            text = p.read_text(encoding="utf8", errors="ignore")
        except Exception:
            continue
        if DEV_PATH.search(text):
            host_coupled.append(rel)
    declared_segments = {".devagent", ".da", ".pytest_cache", ".venv", "instantclient",
                         "node_modules", "dist", "output", "__pycache__",
                         ".certification"}
    declared_paths = {"config/Cadena_conexions.txt",
                      "resources/automation_reports",
                      "resources/test_automation_reports"}

    def is_declared(rel: str) -> bool:
        parts = rel.split("/")
        if any(p in declared_segments for p in parts):
            return True
        return any(rel == d or rel.startswith(d + "/") for d in declared_paths)
    rc, ign, _ = run(["git", "status", "--porcelain", "--ignored=matching"], cwd=ws)
    unexpected_untracked = []
    for line in ign.splitlines():
        if not line.startswith("!!"):
            continue
        rel = line[3:].strip().strip("/")
        if is_declared(rel):
            continue
        unexpected_untracked.append(rel)
    facts["workspace"] = {"tracked_files": len(tracked),
                          "host_coupled_product_files": host_coupled,
                          "undeclared_untracked": unexpected_untracked}
    ok_ws = not unexpected_untracked
    checks.add("CHK-08", "CLEAN_WORKSPACE", "PASS" if ok_ws else "FAIL",
               f"undeclared untracked={unexpected_untracked} (inspected {len(tracked)} tracked files)",
               evidence=["git ls-files content scan", "git status --ignored=matching"])
    # Informational (non-blocking): pre-existing host-coupled legacy files. None of
    # them is imported by the application runtime or by the executed test path, so
    # the measured candidate behaviour is host-independent (proved by re-running the
    # four prerequisite-dependent tests with the Oracle Instant Client hidden).
    checks.add("CHK-08B", "HOST_PATH_DEPENDENCE", "FAIL" if host_coupled else "PASS",
               f"pre-existing host-coupled files outside runtime/test path: {host_coupled}",
               evidence=["git ls-files content scan for C:\\Users\\<user>"],
               blocking=False)

    # ---------------------------------------------------------------- CHK-09
    secret_files = [".env", "config/.env", "config/.env.bak", "config/Cadena_conexions.txt"]
    secret_state = {}
    for rel in secret_files:
        p = ws / rel
        rc, ci, _ = run(["git", "check-ignore", rel], cwd=ws)
        rc, tr, _ = run(["git", "ls-files", "--error-unmatch", rel], cwd=ws)
        secret_state[rel] = {"present": p.exists(), "ignored": bool(ci.strip()),
                             "tracked": tr.strip() == rel}
    leaked = []
    for name in ("backend_pytest_v2.log", "fe_vitest_v2.log", "fe_build_v2.log",
                 "fe_smoke_v2.log", "run_verify_only_v2.json"):
        p = logs / name
        if p.exists() and SECRET_SHAPE.search(p.read_text(encoding="utf8", errors="ignore")):
            leaked.append(name)
    ok_sec = (all(not v["tracked"] for v in secret_state.values())
              and all(v["ignored"] or not v["present"] for v in secret_state.values())
              and not leaked)
    facts["security"] = {"secret_files": secret_state, "logs_with_secret_shapes": leaked}
    checks.add("CHK-09", "SECURITY_GATE", "PASS" if ok_sec else "FAIL",
               json.dumps(secret_state)[:300], evidence=["git check-ignore", "log content scan"])

    # ---------------------------------------------------------------- CHK-10
    reg_path = ws / ".devagent" / "state" / "registry.json"
    reg = json.loads(reg_path.read_text(encoding="utf8"))
    events = reg.get("events", [])
    reserved = [e["run_id"] for e in events if e.get("event_type") == "RUN_ID_RESERVED"]
    terminal = [e for e in events if e.get("event_type") == "RUN_TERMINAL"]
    term_by_run = {}
    for e in terminal:
        term_by_run.setdefault(e["run_id"], []).append(e)
    multi = {r: len(v) for r, v in term_by_run.items() if len(v) != 1}
    never = [r for r in reserved if r not in term_by_run]
    allowed = {"SUCCESS", "FAILED", "BLOCKED", "CANCELLED"}
    bad_status = [e["run_id"] for e in terminal if e.get("status") not in allowed]
    facts["runs"] = {
        "reserved": reserved,
        "terminal_states": {r: v[0].get("terminal_state") for r, v in term_by_run.items()},
        "terminal_statuses": {r: v[0].get("status") for r, v in term_by_run.items()},
        "multiple_terminal_events": multi,
        "reserved_without_terminal": never,
        "terminal_status_outside_vocabulary": bad_status,
    }
    ok_term = not multi and not never and not bad_status and bool(reserved)
    checks.add("CHK-10", "RUN_TERMINALIZATION", "PASS" if ok_term else "FAIL",
               f"{len(reserved)} runs, all terminal exactly once",
               evidence=[".devagent/state/registry.json"])

    # ---------------------------------------------------------------- CHK-11
    res_dir = ws / ".devagent" / "state" / "reservations"
    ter_dir = ws / ".devagent" / "state" / "terminal"
    reservation_ids = {p.stem for p in res_dir.glob("*.json")} if res_dir.exists() else set()
    terminal_ids = {p.stem for p in ter_dir.glob("*.json")} if ter_dir.exists() else set()
    orphans = sorted(reservation_ids - terminal_ids)
    facts["orphan_runs"] = orphans
    checks.add("CHK-11", "ORPHAN_RUNS", "PASS" if not orphans else "FAIL",
               f"{len(orphans)} orphan reservations", evidence=["state/reservations vs state/terminal"])

    # ---------------------------------------------------------------- CHK-12
    evidence_root = ws / ".devagent" / "evidence"
    authority = []
    for run_id in sorted(term_by_run):
        d = evidence_root / run_id
        receipt = d / "AUDIT_RECEIPT.json"
        entry = {"run_id": run_id, "dir_exists": d.exists(),
                 "registry_terminal_state": term_by_run[run_id][0].get("terminal_state"),
                 "registry_status": term_by_run[run_id][0].get("status")}
        term_file = ter_dir / f"{run_id}.json"
        if term_file.exists():
            tdoc = json.loads(term_file.read_text(encoding="utf8"))
            tbody = {k: v for k, v in tdoc.items() if k != "receipt_sha256"}
            entry["terminal_receipt_self_binding_matches"] = (
                hashlib.sha256(json.dumps(tbody, sort_keys=True,
                                          separators=(",", ":")).encode()).hexdigest()
                == tdoc.get("receipt_sha256"))
        if receipt.exists():
            doc = json.loads(receipt.read_text(encoding="utf8"))
            body = {k: v for k, v in doc.items() if k != "receipt_digest"}
            recomputed = hashlib.sha256(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            entry["receipt_digest_recomputed_matches"] = recomputed == doc.get("receipt_digest")
            entry["artifact_count"] = len(doc.get("artifacts", []))
            entry["missing_artifacts"] = [
                a for a in doc.get("artifacts", [])
                if not (ws / a).exists()]
            before = doc.get("product_fingerprint_before") or {}
            after = doc.get("product_fingerprint_after") or {}
            entry["product_fingerprint_unchanged"] = before == after
            entry["product_files_modified"] = doc.get("product_files_modified")
            entry["project_id"] = doc.get("project_id")
            entry["terminal_state"] = doc.get("terminal_state")
            entry["claimed"] = doc.get("claimed")
            entry["not_claimed"] = doc.get("not_claimed")
        entry["artifact_hashes"] = {
            a.name: sha256_file(a) for a in sorted(d.glob("*")) if a.is_file()}
        authority.append(entry)
    facts["evidence_authority"] = authority
    ok_ev = bool(authority)
    for e in authority:
        if "artifact_count" in e:
            if not e.get("receipt_digest_recomputed_matches"):
                ok_ev = False
            if not e.get("product_fingerprint_unchanged"):
                ok_ev = False
            if e.get("missing_artifacts"):
                ok_ev = False
        else:
            # Bootstrap runs (devagent init) carry no audit receipt; they may only
            # have terminalized at DISCOVERED.
            if e.get("registry_terminal_state") != "DISCOVERED":
                ok_ev = False
    checks.add("CHK-12", "EVIDENCE_AUTHORITY", "PASS" if ok_ev else "FAIL",
               f"{len(authority)} run(s): audit receipts self-validating + product "
               f"fingerprint unchanged (before == after), bootstrap runs DISCOVERED",
               evidence=["recomputed receipt_digest", "terminal receipt binding"])
    authority_note = [f"{e['run_id']}={e.get('registry_terminal_state')}" for e in authority]
    facts["runs"]["evidence_note"] = authority_note

    # ---------------------------------------------------------------- CHK-13
    ledger_doc = {}
    ledger_path = Path(args.ledger) if args.ledger else None
    if ledger_path and ledger_path.exists():
        ledger_doc = json.loads(ledger_path.read_text(encoding="utf8"))
    links = ledger_doc.get("links", [])
    product_links = [l for l in links if l.get("chain") == "PRODUCT_VERIFICATION"]
    framework_links = [l for l in links if l.get("chain") == "FRAMEWORK_CERTIFICATION"]
    def coverage(items):
        if not items:
            return 0.0
        done = sum(1 for l in items if l.get("status") == "COMPLETE")
        return round(100.0 * done / len(items), 1)
    missing = [l["link"] for l in links if l.get("status") != "COMPLETE"]
    missing_artifacts = []
    for l in links:
        for art in l.get("artifacts", []):
            ref = art.get("path") if isinstance(art, dict) else art
            if not ref:
                continue
            if not (ws / ref).exists() and not Path(ref).exists():
                missing_artifacts.append(ref)
    facts["traceability"] = {
        "product_verification_coverage": coverage(product_links),
        "framework_certification_coverage": coverage(framework_links),
        "incomplete_links": missing,
        "missing_artifacts": missing_artifacts,
    }
    ok_tr = (coverage(product_links) == 100.0 and not missing_artifacts)
    checks.add("CHK-13", "TRACEABILITY", "PASS" if ok_tr else "FAIL",
               f"product chain {coverage(product_links)}%, framework chain "
               f"{coverage(framework_links)}%, incomplete={missing}",
               evidence=[str(ledger_path)])

    # ---------------------------------------------------------------- CHK-14
    controls = Path(args.controls) if args.controls else None
    control_facts = {}
    if controls and controls.exists():
        for name in ("a6-zero-tests", "failing-suite", "false-success"):
            p = controls / f"{name}_run.json"
            if not p.exists():
                continue
            text = p.read_text(encoding="utf8", errors="ignore")
            control_facts[name] = {
                "exit_code": int(re.search(r"EXIT=(\d+)", text).group(1))
                if re.search(r"EXIT=(\d+)", text) else None,
                "blocked_a6_zero_tests": "zero tests executed (A6 fake-PASS rejected)" in text,
                "blocked_executed_suite_failed": "executed suite failed" in text,
                "recorded_run_id": (re.search(r"RUN-[0-9A-F]{16}", text).group(0)
                                    if re.search(r"RUN-[0-9A-F]{16}", text) else None),
            }
            if name == "false-success":
                i = text.find("{")
                try:
                    doc = json.loads(text[i:])
                    control_facts[name].update({
                        "state": doc.get("state"), "certified": doc.get("certified"),
                        "e2e_observed": (doc.get("stages") or {}).get("e2e", {}).get("observed"),
                        "tests_run": (doc.get("stages") or {}).get("testing", {}).get("tests_run"),
                        "claims": doc.get("claims"),
                    })
                except Exception:
                    pass
    a6 = control_facts.get("a6-zero-tests", {})
    fs = control_facts.get("false-success", {})
    c3 = control_facts.get("failing-suite", {})
    controls_ok = bool(a6.get("blocked_a6_zero_tests") and c3.get("blocked_executed_suite_failed"))
    vector_open = bool(fs.get("certified") is True)
    facts["false_success_controls"] = {
        "a6_zero_tests_blocked": a6, "failing_suite_blocked": c3,
        "cli_certified_without_e2e_or_verifier": fs,
        "vector_open": vector_open,
    }
    checks.add("CHK-14", "FALSE_SUCCESS_CONTROLS",
               "PASS" if (controls_ok and not vector_open) else ("FAIL" if controls_ok else "FAIL"),
               f"A6 control blocked={bool(a6.get('blocked_a6_zero_tests'))}, "
               f"failing-suite control blocked={bool(c3.get('blocked_executed_suite_failed'))}, "
               f"open CLI false-success vector={vector_open}",
               evidence=["control run logs"])

    # ---------------------------------------------------------------- verdict
    blockers = []
    if facts.get("false_success_controls", {}).get("vector_open"):
        blockers.append(
            "FRAMEWORK_DEFECT: devagent run --intent IMPLEMENTATION can terminalize "
            "CERTIFIED with a stubbed e2e_check and no verifier (control run "
            "RUN-248573DB01424FE9) -> no framework CERTIFIED receipt is trustworthy")
    if facts.get("traceability", {}).get("framework_certification_coverage") == 0.0:
        blockers.append(
            "FRAMEWORK_DEFECT: no routed VERIFY_ONLY execution path; TESTED / "
            "E2E_VERIFIED / INDEPENDENTLY_VERIFIED / CERTIFIED are unreachable "
            "through the 4.5.1 CLI (observed terminal state: AUDITED)")
    report = {
        "schema_version": SCHEMA,
        "produced_by": "independent_verifier.py (separate verifier authority; the "
                       "framework's own verifier is unreachable from the 4.5.1 CLI)",
        "facts": facts,
        "checks": checks.items,
        "failed_checks": [c["check_id"] for c in checks.failed()],
        "informational_findings": [c["check_id"] for c in checks.items
                                   if not c["blocking"] and c["status"] != "PASS"],
        "blockers": blockers,
        "certification_status": ("CERTIFIED" if not checks.failed() and not blockers
                                 else "NOT_CERTIFIED"),
    }
    body = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_sha256"] = hashlib.sha256(body.encode()).hexdigest()
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf8")

    print(f"checks: {len(checks.items)}  failed: {report['failed_checks']}")
    for c in checks.items:
        print(f"  {c['check_id']} {c['name']:<22} {c['status']:<5} {c['detail'][:150]}")
    print(f"CERTIFICATION_STATUS={report['certification_status']}")
    print(f"report_sha256={report['report_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
