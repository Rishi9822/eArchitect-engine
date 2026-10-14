#!/usr/bin/env python
"""
CLI script to run the 20-plot regression test corpus and generate CSV reports.

Usage:
    python scripts/run_batch_corpus.py [--csv output_path.csv]
"""
import os
import sys
import argparse

# Ensure engine package is importable
ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ENGINE_ROOT not in sys.path:
    sys.path.insert(0, ENGINE_ROOT)

from app.testing.batch_runner import run_batch_corpus


def main():
    parser = argparse.ArgumentParser(description="Run eArchitect 20-plot test corpus and emit regression metrics.")
    parser.add_argument(
        "--csv",
        type=str,
        default=os.path.join(ENGINE_ROOT, "reports", "corpus_results.csv"),
        help="Path where the CSV report will be saved (default: reports/corpus_results.csv)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress console progress output",
    )
    args = parser.parse_args()

    results = run_batch_corpus(
        export_csv_path=args.csv,
        verbose=not args.quiet,
    )

    summary = results["summary"]
    if summary["pass_rate_pct"] < 100.0:
        print(f"FAILED: Only {summary['valid_plots']}/{summary['total_plots']} layouts were valid.")
        sys.exit(1)
    else:
        print("SUCCESS: 100% of test corpus plots passed all regression gates.")
        sys.exit(0)


if __name__ == "__main__":
    main()
