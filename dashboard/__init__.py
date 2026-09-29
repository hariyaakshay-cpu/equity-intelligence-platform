"""Read-only Flask dashboard for equity_intel's scan results.

This package never imports sqlite3 and never imports equity_intel's
persistence.connection.get_connection (the writable one) -- only
get_read_only_connection. See equity_intel/tests/test_db_connection_boundary.py
and equity_intel/tests/test_import_boundaries.py, both of which are
extended to scan this package too.
"""
