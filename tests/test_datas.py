from datetime import datetime

from app.services.datas import SP_TZ, calendario_referencia, resolver_data

DOM = datetime(2026, 11, 8, 10, 0, tzinfo=SP_TZ)    # domingo
SEG = datetime(2026, 11, 9, 16, 45, tzinfo=SP_TZ)   # segunda do incidente (Levindo)


def test_ontem_incidente_levindo():
    # modelo mandou 10/10/2026; o certo era o GAS do domingo 08/11
    assert resolver_data("ontem", SEG) == "2026-11-08"
    assert resolver_data("Ontem", SEG) == "2026-11-08"


def test_relativos_simples():
    assert resolver_data("hoje", SEG) == "2026-11-09"
    assert resolver_data("anteontem", SEG) == "2026-11-07"
    assert resolver_data("amanhã", SEG) == "2026-11-10"


def test_domingo():
    assert resolver_data("domingo", DOM) == "2026-11-08"
    assert resolver_data("domingo passado", DOM) == "2026-11-01"
    assert resolver_data("domingo passado", SEG) == "2026-11-08"
    assert resolver_data("último domingo", SEG) == "2026-11-08"
    assert resolver_data("domingo", SEG) == "2026-11-08"


def test_formatos_explicitos():
    assert resolver_data("2026-11-08", SEG) == "2026-11-08"
    assert resolver_data("08/11", SEG) == "2026-11-08"
    assert resolver_data("8/11/2026", SEG) == "2026-11-08"
    assert resolver_data("08/11/26", SEG) == "2026-11-08"


def test_dd_mm_no_futuro_distante_vai_pro_ano_anterior():
    assert resolver_data("28/12", SEG) == "2025-12-28"


def test_lixo_devolve_none():
    assert resolver_data("o de semana que vem talvez", SEG) is None
    assert resolver_data("31/02", SEG) is None
    assert resolver_data("", SEG) is None


def test_calendario():
    c = calendario_referencia(SEG)
    assert "Ontem: domingo, 08/11/2026" in c
    assert "Amanhã: terça-feira, 10/11/2026" in c
    assert "Último domingo (o de hoje, se hoje for domingo): 08/11/2026" in c
    assert "Domingo anterior a esse: 01/11/2026" in c
