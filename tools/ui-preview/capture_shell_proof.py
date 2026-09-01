"""Capture the deterministic UI-012 TARS/95 physical shell proof."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]
PROOF_ROOT = REPO_ROOT / "Documentation" / "review-proofs" / "UI-012"
PROOF_PATH = PROOF_ROOT / "TARS95_shell_proof_480x320.png"


def main() -> int:
    PROOF_ROOT.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(REPO_ROOT / "tools" / "ui-preview" / "device_preview.py"),
        "--app", "eyes",
        "--size", "480x320",
        "--state", "listening",
        "--battery", "78",
        "--alert", "none",
        "--connectivity", "online",
        "--headless",
        "--frames", "3",
        "--screenshot", str(PROOF_PATH),
    ]
    environment = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    result = subprocess.run(command, cwd=REPO_ROOT, env=environment, check=False)
    if result.returncode:
        return result.returncode

    with Image.open(PROOF_PATH) as image:
        if image.size != (480, 320):
            raise RuntimeError(f"Expected 480x320 proof, received {image.size}")

    manifest = {
        "action": "UI-012",
        "file": PROOF_PATH.name,
        "dimensions": [480, 320],
        "surface": "eyes",
        "fixture": {
            "machine_state": "listening",
            "battery": 78,
            "alert": "none",
            "connectivity": "online",
        },
        "sha256": hashlib.sha256(PROOF_PATH.read_bytes()).hexdigest(),
    }
    (PROOF_ROOT / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
    )
    print(f"PASS: UI-012 proof captured at {PROOF_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
