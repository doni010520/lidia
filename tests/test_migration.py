"""Testes para scripts/migrate_from_supabase.py - helpers de parse."""
from datetime import date, datetime

from scripts.migrate_from_supabase import _date, _dt, _int


class TestParseDate:
    def test_iso_date(self):
        assert _date("2025-06-15") == date(2025, 6, 15)

    def test_iso_datetime(self):
        assert _date("2025-06-15T14:30:00Z") == date(2025, 6, 15)

    def test_none(self):
        assert _date(None) is None

    def test_empty(self):
        assert _date("") is None

    def test_invalid(self):
        assert _date("not-a-date") is None


class TestParseDatetime:
    def test_iso(self):
        result = _dt("2025-06-15T14:30:00Z")
        assert result is not None
        assert result.year == 2025

    def test_none(self):
        assert _dt(None) is None


class TestParseInt:
    def test_valid(self):
        assert _int("42") == 42

    def test_none(self):
        assert _int(None) is None

    def test_empty(self):
        assert _int("") is None

    def test_invalid(self):
        assert _int("abc") is None
