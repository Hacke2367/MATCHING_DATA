"""Pro-Match Identity Engine — CLI Entry Point.

Usage:
    python main.py --anchor data/actual_user/boss.json \
                   --candidates-dir data/potential_matches/
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from engine.errors import FatalOrchestrationError
from engine.orchestrator import run_batch

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pro-match")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pro-match",
        description="Pro-Match Identity Engine — match a User KYC profile against adverse media candidates.",
    )
    parser.add_argument(
        "--anchor",
        required=True,
        metavar="PATH",
        help="Path to the User KYC JSON file (Source A).",
    )
    parser.add_argument(
        "--candidates-dir",
        required=True,
        metavar="DIR",
        help="Directory containing Candidate JSON files (Source B).",
    )
    return parser.parse_args()


def _verdict_badge(color: str) -> str:
    return {"GREEN": "✓ GREEN", "AMBER": "~ AMBER", "RED": "✗ RED"}.get(color, color)


def _print_summary(result, saved_path: str | None) -> None:
    meta = result.run_metadata
    total = meta.get("candidate_count", "?")
    version = meta.get("engine_version", "?")

    print()
    print("=" * 60)
    print("  PRO-MATCH  ·  BATCH COMPLETE")
    print("=" * 60)
    print(f"  Engine version   : {version}")
    print(f"  Candidates run   : {total}")
    print(f"  Started          : {meta.get('run_started_utc', '')}")
    print(f"  Finished         : {meta.get('run_finished_utc', '')}")
    print("-" * 60)

    if result.best_match is None:
        print("  Best match       : NONE  (all candidates hard-rejected or batch empty)")
    else:
        bm = result.best_match
        confidence_pct = f"{bm.final_confidence * 100:.1f}%"
        print(f"  Best match       : {bm.candidate_summary.full_name}")
        print(f"  Confidence       : {confidence_pct}")
        print(f"  Verdict          : {_verdict_badge(bm.verdict_color)}  —  {bm.verdict_label}")
        print(f"  Tier reached     : {bm.tier_reached}")
        if bm.llm_verdict:
            print(f"  LLM verdict      : {bm.llm_verdict}")

    print("-" * 60)
    if saved_path:
        print(f"  Report saved to  : {saved_path}")
    else:
        print("  Report saved to  : [NOT SAVED — disk write failed or empty batch]")
    print("=" * 60)
    print()


def main() -> int:
    args = _parse_args()

    anchor_path = str(Path(args.anchor))
    candidates_dir = str(Path(args.candidates_dir))

    logger.info("Starting batch: anchor=%s  candidates_dir=%s", anchor_path, candidates_dir)

    try:
        result, saved_path = run_batch(anchor_path, candidates_dir)
    except FatalOrchestrationError as exc:
        logger.error("Fatal pipeline error: %s", exc)
        logger.error("Anchor file: %s", exc.user_file_path)
        if exc.cause:
            logger.error("Caused by: %s: %s", type(exc.cause).__name__, exc.cause)
        print(f"\nERROR: {exc}\n", file=sys.stderr)
        return 1
    except Exception as exc:
        logger.critical("Unexpected critical failure: %s: %s", type(exc).__name__, exc)
        print(f"\nCRITICAL ERROR: {type(exc).__name__}: {exc}\n", file=sys.stderr)
        return 2

    _print_summary(result, saved_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
