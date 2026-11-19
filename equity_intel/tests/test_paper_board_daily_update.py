from datetime import date

from equity_intel.paper_board import daily_update as du


def test_merge_adds_new_days_replaces_overlap_keeps_history():
    old = {"2026-11-13": (1, 1, 1, 1, 10), "2026-11-16": (2, 2, 2, 2, 20), "2026-11-17": (3, 3, 3, 3, 30)}
    new = {"2026-11-17": (3, 3, 3, 3.5, 31), "2026-11-18": (4, 4, 4, 4, 40)}
    m = du.merge(old, new)
    assert list(m) == ["2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18"]
    assert m["2026-11-17"] == (3, 3, 3, 3.5, 31) and m["2026-11-13"] == (1, 1, 1, 1, 10)


def test_fetch_window_overlaps_seven_days():
    assert du.fetch_from(date(2026, 11, 18)) == date(2026, 11, 11)


def test_calendar_infers_missing_weekdays_so_staleness_is_visible():
    known = [date(2026, 11, 13), date(2026, 11, 16), date(2026, 11, 17)]
    s, inferred = du.session_calendar(known, date(2026, 11, 19))
    assert s[-3:] == [date(2026, 11, 17), date(2026, 11, 18), date(2026, 11, 19)] and inferred == [date(2026, 11, 18)]
    s, inferred = du.session_calendar(known + [date(2026, 11, 18)], date(2026, 11, 19))
    assert inferred == [] and s[-2] == date(2026, 11, 18)
    s, inferred = du.session_calendar([date(2026, 11, 20)], date(2026, 11, 23))      # Fri file, Mon run: no weekend gap
    assert inferred == [] and s == [date(2026, 11, 20), date(2026, 11, 23)]
