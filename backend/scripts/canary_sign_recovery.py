"""Explicit operator CLI. Diagnose/plan/export are read-only; apply requires an exact approval hash."""

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import SessionLocal, begin_report_snapshot
from app import canary_sign_recovery as recovery


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("diagnose")
    commands.add_parser("receipts")
    export = commands.add_parser(
        "export-evidence",
        help="Run only against a separately restored and verified backup",
    )
    export.add_argument("--request", type=uuid.UUID, required=True)
    export.add_argument("--artifact", choices=recovery.ARTIFACTS, required=True)
    export.add_argument(
        "--source-label",
        required=True,
        help="Backup identity/checksum and verification reference",
    )
    export.add_argument("--output-dir", type=Path, required=True)
    plan = commands.add_parser(
        "plan", help="Dry run: produces a reviewable plan without applying it"
    )
    plan.add_argument("--request", type=uuid.UUID, required=True)
    plan.add_argument("--artifact", choices=recovery.ARTIFACTS, required=True)
    plan.add_argument("--action", choices=("baseline", "restore"), required=True)
    plan.add_argument("--actor", type=uuid.UUID, required=True)
    plan.add_argument("--reason", required=True)
    plan.add_argument("--evidence-dir", type=Path, required=True)
    plan.add_argument("--operation-id", type=uuid.UUID, default=None)
    apply = commands.add_parser("apply")
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--evidence-dir", type=Path, required=True)
    apply.add_argument(
        "--approve-plan", required=True, help="SHA-256 of the exact reviewed plan"
    )
    args = parser.parse_args()
    try:
        with SessionLocal() as db:
            if args.command != "apply":
                begin_report_snapshot(db)
            if args.command == "diagnose":
                result = recovery.diagnose(db)
            elif args.command == "receipts":
                result = recovery.receipts(db)
            elif args.command == "export-evidence":
                proof, raw = recovery.evidence(
                    db, args.request, args.artifact, args.source_label
                )
                args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
                for name, data in [
                    ("evidence.json", json.dumps(proof, indent=2).encode()),
                    ("artifact.pdf", raw),
                ]:
                    fd = os.open(
                        args.output_dir / name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                    )
                    with os.fdopen(fd, "wb") as out:
                        out.write(data)
                result = proof
            else:
                raw = (args.evidence_dir / "artifact.pdf").read_bytes()
                proof = json.loads((args.evidence_dir / "evidence.json").read_text())
                if args.command == "plan":
                    result = recovery.prepare(
                        db,
                        request_id=args.request,
                        artifact=args.artifact,
                        action=args.action,
                        actor_id=args.actor,
                        reason=args.reason,
                        proof=proof,
                        raw=raw,
                        operation_id=args.operation_id or uuid.uuid4(),
                    )
                else:
                    reviewed = json.loads(args.plan.read_text())
                    if proof != reviewed["evidence"]:
                        raise ValueError("Evidence metadata changed since review")
                    result = recovery.apply(
                        db, reviewed, raw, approved_sha256=args.approve_plan
                    )
                    db.commit()
            print(json.dumps(result, sort_keys=True, indent=2))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "detail": (
                        str(exc)
                        if isinstance(exc, ValueError)
                        else "Operation failed; no success confirmed"
                    ),
                }
            ),
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
