"""Export the FastAPI contract used by service clients and contract tests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.main import backend


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/openapi.json"),
        help="Path for the exported OpenAPI document",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(backend.openapi(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
