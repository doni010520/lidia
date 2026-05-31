"""Testes para scripts/migrate_from_supabase.py — helpers de parse."""
from datetime import date

from scripts.migrate_from_supabase import _parse_date_safe


class TestParseDateSafe:
    def test_iso_date(self):
        assert _parse_date_safe("2025-06-15") == date(2025, 6, 15)

    def test_iso_datetime(self):
        assert _parse_date_safe("2025-06-15T14:30:00Z") == date(2025, 6, 15)

    def test_none(self):
        assert _parse_date_safe(None) is None

    def test_empty(self):
        assert _parse_date_safe("") is None

    def test_invalid(self):
        assert _parse_date_safe("not-a-date") is None
