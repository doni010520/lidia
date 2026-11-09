"""Datas relativas resolvidas em código, nunca pelo modelo.

Incidente 09/11/2026 (Levindo): "vc tem o acompanhamento de ontem" num domingo
09/11 virou GAS de 10/10/2026 — o modelo fez a conta de "ontem" e errou o mês.
Duas defesas:
1. `calendario_referencia` — o prompt recebe ontem/amanhã/último domingo já
   calculados, em vez de só "hoje".
2. `resolver_data` — a tool aceita "ontem", "domingo passado", "08/11" etc. e
   converte aqui, no fuso de São Paulo. Se o modelo mandar o texto da pessoa,
   a conta é nossa.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

SP_TZ = ZoneInfo("America/Sao_Paulo")

_DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
         "sexta-feira", "sábado", "domingo"]
# chave sem acento/sufixo → weekday()
_DIA_IDX = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3,
            "sexta": 4, "sabado": 5, "domingo": 6}


def hoje_sp(now: datetime | None = None) -> date:
    return (now or datetime.now(SP_TZ)).astimezone(SP_TZ).date()


def _br(d: date) -> str:
    return f"{_DIAS[d.weekday()]}, {d:%d/%m/%Y}"


def _ultimo(d: date, weekday: int, incluir_hoje: bool) -> date:
    delta = (d.weekday() - weekday) % 7
    if delta == 0 and not incluir_hoje:
        delta = 7
    return d - timedelta(days=delta)


def calendario_referencia(now: datetime | None = None) -> str:
    """Linhas prontas pro prompt: o modelo copia a data, não calcula."""
    h = hoje_sp(now)
    dom = _ultimo(h, 6, incluir_hoje=True)
    return "\n".join([
        f"Ontem: {_br(h - timedelta(days=1))}",
        f"Amanhã: {_br(h + timedelta(days=1))}",
        f"Último domingo (o de hoje, se hoje for domingo): {dom:%d/%m/%Y}",
        f"Domingo anterior a esse: {dom - timedelta(days=7):%d/%m/%Y}",
        "Datas relativas (ontem, domingo passado, semana que vem): use as datas "
        "acima, nunca calcule. Nas ferramentas, passe a data como a pessoa "
        "disse (ex: \"ontem\") ou no formato YYYY-MM-DD.",
    ])


def _norm(s: str) -> str:
    t = unicodedata.normalize("NFKD", s.lower().strip())
    return "".join(c for c in t if not unicodedata.combining(c))


def resolver_data(texto: str | None, now: datetime | None = None) -> str | None:
    """Converte o que a pessoa/modelo mandou em YYYY-MM-DD; None se não entender.

    Aceita: hoje, ontem, anteontem, amanhã, "domingo passado/último domingo",
    "domingo" (o mais recente, inclusive hoje), dd/mm, dd/mm/aa(aa), YYYY-MM-DD.
    dd/mm sem ano que cairia no futuro é do ano anterior (material é do passado).
    """
    if not texto:
        return None
    t = _norm(texto)
    h = hoje_sp(now)

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
        try:
            return date.fromisoformat(t).isoformat()
        except ValueError:
            return None

    fixos = {"hoje": 0, "ontem": -1, "anteontem": -2, "amanha": 1}
    if t in fixos:
        return (h + timedelta(days=fixos[t])).isoformat()

    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?", t)
    if m:
        dia, mes, ano = int(m[1]), int(m[2]), m[3]
        try:
            if ano:
                a = int(ano)
                return date(a + 2000 if a < 100 else a, mes, dia).isoformat()
            d = date(h.year, mes, dia)
            if d > h + timedelta(days=7):
                d = date(h.year - 1, mes, dia)
            return d.isoformat()
        except ValueError:
            return None

    for nome, wd in _DIA_IDX.items():
        if re.search(rf"\b{nome}\b", t):
            passado = re.search(r"passad|ultim|anterior", t)
            if passado:
                return _ultimo(h, wd, incluir_hoje=False).isoformat()
            return _ultimo(h, wd, incluir_hoje=True).isoformat()
    return None
