"""Run within the API environment: python -m scripts.commercial_readiness."""
import json
from app.core.commercial import report

if __name__ == "__main__":
    print(json.dumps(report(), ensure_ascii=False, indent=2))
