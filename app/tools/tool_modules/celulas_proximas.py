"""Tool: celulas_proximas — sugere células por localização.

Aceita TANTO coordenadas (lat/lng) QUANTO endereço por texto (bairro, rua, etc.).
Se receber texto, geocodifica via Nominatim (OpenStreetMap) antes de consultar
GET /cells/near no Diacon.
"""
from __future__ import annotations

import httpx
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import diacon_client

# Referência para geocoding: Região Metropolitana do Recife (RMR)
_GEOCODE_VIEWBOX = "-35.1,-8.4,-34.8,-7.9"  # Recife/Jaboatão/Olinda/Paulista

# Municípios da RMR que aparecem no texto do usuário. Se um deles já vier
# escrito, NÃO forçamos "Recife" — respeitamos a cidade informada.
_MUNICIPIOS_RMR = (
    "jaboat",  # Jaboatão dos Guararapes
    "olinda",
    "paulista",
    "camaragibe",
    "recife",
    "cabo",  # Cabo de Santo Agostinho
    "abreu e lima",
    "igarassu",
    "moreno",
    "ipojuca",
    "são lourenço",
    "sao lourenco",
)

# Bairros/localidades ambíguos que NÃO ficam em Recife. Forçar "Recife" no
# geocoding (bug antigo) jogava a busca para o município errado ou zerava o
# resultado. "Piedade" é o caso crítico: fica em Jaboatão dos Guararapes,
# onde está a paróquia e a maior parte das células.
_MUNICIPIO_POR_BAIRRO = {
    "piedade": "Jaboatão dos Guararapes",
    "candeias": "Jaboatão dos Guararapes",
    "prazeres": "Jaboatão dos Guararapes",
    "cavaleiro": "Jaboatão dos Guararapes",
    "curado": "Jaboatão dos Guararapes",
    "barra de jangada": "Jaboatão dos Guararapes",
    "muribeca": "Jaboatão dos Guararapes",
}


def _build_queries(address: str) -> list[str]:
    """Monta variações de busca, da mais específica para a mais genérica.

    Regras:
    - Se o usuário já citou um município da RMR, respeita a cidade e só
      complementa com estado/país (nunca sobrepõe "Recife").
    - Se citou um bairro ambíguo conhecido (ex.: Piedade), ancora no
      município correto (Jaboatão) antes de cair para Recife.
    """
    a = address.strip().rstrip(",")
    low = a.lower()
    queries: list[str] = []

    if any(m in low for m in _MUNICIPIOS_RMR):
        # Já tem cidade no texto — não force outra.
        queries.append(f"{a}, Pernambuco, Brasil")
    else:
        for bairro, municipio in _MUNICIPIO_POR_BAIRRO.items():
            if bairro in low:
                queries.append(f"{a}, {municipio}, Pernambuco, Brasil")
                break
        # Ainda tenta Recife (maioria dos bairros é de Recife)...
        queries.append(f"{a}, Recife, Pernambuco, Brasil")
        # ...e, por fim, só o estado, para pegar qualquer cidade da RMR.
        queries.append(f"{a}, Pernambuco, Brasil")

    # Dedup preservando ordem.
    seen: set[str] = set()
    return [q for q in queries if not (q in seen or seen.add(q))]


async def _geocode(address: str) -> tuple[float, float] | None:
    """Geocodifica endereço via Nominatim. Retorna (lat, lng) ou None.

    Tenta cada variação de query; para cada uma, primeiro com o viewbox como
    limite rígido (bounded=1) e, se não achar, como simples viés (bounded=0),
    para não descartar pontos na borda da RMR.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for query in _build_queries(address):
                for bounded in (1, 0):
                    resp = await client.get(
                        "https://nominatim.openstreetmap.org/search",
                        params={
                            "q": query,
                            "format": "json",
                            "limit": 1,
                            "countrycodes": "br",
                            "viewbox": _GEOCODE_VIEWBOX,
                            "bounded": bounded,
                        },
                        headers={"User-Agent": "LidIA-PAES/1.0"},
                    )
                    resp.raise_for_status()
                    results = resp.json()
                    if results:
                        logger.info(
                            f"celulas_proximas geocode ok: '{query}' "
                            f"(bounded={bounded}) → "
                            f"{results[0]['lat']},{results[0]['lon']}"
                        )
                        return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        logger.warning(f"celulas_proximas geocode falhou: {e}")
    return None


async def execute(args: dict, phone: str, db: AsyncSession) -> str:
    lat = args.get("lat")
    lng = args.get("lng")
    endereco = args.get("endereco") or args.get("address") or ""

    # Tenta usar lat/lng se vieram como números válidos
    if lat is not None and lng is not None:
        try:
            lat = float(lat)
            lng = float(lng)
        except (TypeError, ValueError):
            lat, lng = None, None

    # Se não tem coordenadas, geocodifica o endereço
    if lat is None or lng is None:
        if not endereco.strip():
            return (
                "Preciso saber o bairro ou a região onde você mora "
                "para buscar a célula mais próxima. Pode me informar?"
            )
        coords = await _geocode(endereco)
        if coords is None:
            return (
                f"Não consegui localizar \"{endereco}\" no mapa. "
                "Pode me dizer o bairro de outro jeito, ou um ponto de referência?"
            )
        lat, lng = coords

    limit = int(args.get("limit") or 5)
    limit = max(1, min(20, limit))

    if not diacon_client.is_enabled():
        return "Erro: integração Diacon não configurada."

    try:
        data = await diacon_client.cells_near(lat, lng, limit=limit)
    except diacon_client.DiaconError as e:
        logger.warning(f"celulas_proximas: {e.code} {e}")
        return "Não consegui buscar células agora. Tenta de novo em alguns segundos."

    cells = data.get("cells", [])
    if not cells:
        return (
            f"Não encontrei nenhuma célula perto de \"{endereco or 'essa localização'}\". "
            "Quer que eu encaminhe para a equipe de células te ajudar?"
        )

    lines = [f"Encontrei {len(cells)} célula(s) perto de {endereco or 'você'}:\n"]
    for c in cells:
        nome = c.get("name") or "Célula"
        dia = c.get("meeting_day_label") or ""
        hora = c.get("meeting_time") or ""
        end = c.get("meeting_address") or ""
        bairro = c.get("neighborhood") or ""
        lider = c.get("leader_first_name") or ""
        dist = c.get("distance_km")

        parts = [f"📍 *{nome}*"]
        if dist is not None:
            parts.append(f"{dist:.1f} km")
        if dia and hora:
            parts.append(f"reúne {dia} às {hora}")
        if end:
            local = end
            if bairro and bairro not in end:
                local = f"{end} · {bairro}"
            parts.append(local)
        if lider:
            parts.append(f"líder: {lider}")
        lines.append(" — ".join(parts))

    return "\n\n".join(lines)
