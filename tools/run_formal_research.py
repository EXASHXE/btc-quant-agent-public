from __future__ import annotations

import argparse
import json

from btc_quant_agent.formal_research import run_formal_job_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Current formal P5/P6 research workflow")
    parser.add_argument("--job", required=True, help="versioned job JSON with explicit protocol")
    parser.add_argument("--output", required=True)
    parser.add_argument("--registry", help="existing authoritative P5 registry")
    parser.add_argument("--record-decision", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_formal_job_file(
            args.job, output_directory=args.output, registry_path=args.registry,
            record_decision=args.record_decision,
        )
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        print(json.dumps({"classification": "NOT_TESTABLE_FOR_NEW_PROMOTION", "error": str(exc)}))
        return 2
    print(json.dumps(result.status(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
