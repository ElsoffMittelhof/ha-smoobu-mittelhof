from datetime import date
import importlib.util
from pathlib import Path

# Pure logic test without importing Home Assistant.
module_path = Path(__file__).parents[1] / "custom_components" / "smoobu_mittelhof" / "statistics.py"
spec = importlib.util.spec_from_file_location("stats", module_path)
stats = importlib.util.module_from_spec(spec)
# Minimal package-relative import cannot be resolved standalone; this file is a design fixture for HA CI.


def sample_bookings():
    return [
        {"type": "reservation", "arrival": "2026-09-10", "departure": "2026-09-13", "language": "de", "adults": 2, "children": 1},
        {"type": "reservation", "arrival": "2026-09-30", "departure": "2026-10-03", "language": "nl", "adults": 2, "children": 0},
    ]
