from datetime import date
from pathlib import Path
import importlib.util
import sys
import types

PACKAGE = "smoobu_stats_test"
package = types.ModuleType(PACKAGE)
package.__path__ = []
sys.modules[PACKAGE] = package

const = types.ModuleType(f"{PACKAGE}.const")
const.VALID_BOOKING_TYPES = {"reservation", "modification of booking"}
sys.modules[const.__name__] = const

bookings = types.ModuleType(f"{PACKAGE}.bookings")


def parse_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


bookings.parse_date = parse_date
sys.modules[bookings.__name__] = bookings

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "smoobu_mittelhof" / "statistics.py"
spec = importlib.util.spec_from_file_location(f"{PACKAGE}.statistics", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def run() -> None:
    # Calendar-month reporting must include the night crossing from 01.10. to 02.10.
    query_from, query_to, calc_from, calc_to = module.statistics_period(
        2026, 10, module.MODE_CALENDAR
    )
    assert query_from == date(2026, 10, 1)
    assert query_to == date(2026, 11, 1)
    assert calc_from == date(2026, 10, 1)
    assert calc_to == date(2026, 11, 1)

    booking = {
        "id": 1,
        "type": "reservation",
        "arrival": "2026-09-27",
        "departure": "2026-10-02",
        "adults": 2,
        "children": 0,
        "language": "nl",
        "apartment": {"id": 123},
    }

    result = module.calculate_statistics([booking], 2026, 10, apartment_ids=[123])
    assert result["mode"] == module.MODE_CALENDAR
    assert result["total_arrivals"] == 0
    assert result["total_overnight_stays"] == 2
    assert result["language_stats"] == [
        {"language": "nl", "totalOvernightStays": 2, "totalArrivals": 0}
    ]

    # September gets the four September nights: 27/28, 28/29, 29/30 and 30/01.
    september = module.calculate_statistics([booking], 2026, 9, apartment_ids=[123])
    assert september["total_overnight_stays"] == 8
    assert september["total_arrivals"] == 2


if __name__ == "__main__":
    run()
    print("statistics month-boundary logic: OK")
