import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in ["", "libs", "web", "services/car-service", "services/customer-service", "services/sales-service",
          "services/financing-service"]:
    sys.path.insert(0, str(ROOT / p))
