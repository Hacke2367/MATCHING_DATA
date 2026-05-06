"""Upload bytes → temp filesystem paths consumed by run_batch().

No engine imports. Pure stdlib IO.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Callable


def write_uploads_to_temp(
    anchor_bytes: bytes,
    anchor_name: str,
    candidate_files: list[tuple[bytes, str]],
) -> tuple[str, str, Callable[[], None]]:
    """Write uploaded file content to an isolated temp directory.

    Returns (anchor_path, candidates_dir, cleanup_fn).
    Call cleanup_fn() after run_batch() completes to remove temp files.
    """
    tmp_root = tempfile.mkdtemp(prefix="promatch_")
    anchor_dir = Path(tmp_root) / "anchor"
    cands_dir = Path(tmp_root) / "candidates"
    anchor_dir.mkdir()
    cands_dir.mkdir()

    anchor_path = anchor_dir / anchor_name
    anchor_path.write_bytes(anchor_bytes)

    for content, fname in candidate_files:
        (cands_dir / fname).write_bytes(content)

    def cleanup() -> None:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return str(anchor_path), str(cands_dir), cleanup
