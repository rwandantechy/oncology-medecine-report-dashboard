"""CLI entry for the ingestion pipeline."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from src.pipeline.flows.ingest import ingest_flow
from src.pipeline.review import service as review_service

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the OncoSmart ingest pipeline.")
    parser.add_argument(
        "--list-pending",
        action="store_true",
        help="List drafts waiting in the review queue.",
    )
    parser.add_argument(
        "--approve",
        metavar="RECORD_ID",
        help="Approve a draft from the review queue into the recalls table.",
    )
    parser.add_argument(
        "--reject",
        metavar="RECORD_ID",
        help="Reject a draft in the review queue.",
    )
    args = parser.parse_args(argv)

    if args.list_pending:
        pending = review_service.pending()
        if not pending:
            print("No pending drafts.")
            return 0
        for alert in pending:
            errors = "; ".join(alert.validation_errors) or "none"
            print(f"{alert.record_id}\t{alert.product_name}\t{errors}")
        return 0

    if args.approve:
        ok = review_service.approve(args.approve)
        if not ok:
            logger.error("Record not found in review queue: %s", args.approve)
            return 1
        print(f"Approved {args.approve}")
        return 0

    if args.reject:
        ok = review_service.reject(args.reject)
        if not ok:
            logger.error("Record not found in review queue: %s", args.reject)
            return 1
        print(f"Rejected {args.reject}")
        return 0

    summary = ingest_flow()
    print(summary)
    # Partial source failures (timeouts, site changes) are expected. Only fail
    # the process when nothing useful was written.
    wrote = summary.get("approved", 0) + summary.get("review", 0)
    if wrote > 0:
        return 0
    return 1 if summary.get("errors", 0) else 0


if __name__ == "__main__":
    sys.exit(main())
