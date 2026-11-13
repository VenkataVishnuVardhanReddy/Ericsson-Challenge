"""Run Distill web server: python -m distill"""
from __future__ import annotations

import os
import uvicorn


def main() -> None:
    port = int(os.environ.get("DISTILL_PORT", 8000))
    host = os.environ.get("DISTILL_HOST", "127.0.0.1")
    uvicorn.run("distill.app:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
