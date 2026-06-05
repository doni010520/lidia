"""Tool: celulas_proximas — sugere células por geolocalização.

GET /cells/near?lat=&lng=&limit= — Diacon ordena por distância.
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import diacon_client


async def execute(args: dict, phone: str, db: AsyncSession) -> str:
    try:
        lat = float(args.get("lat"))
        lng = float(args.get("lng"))
    except (TypeError, ValueError):
        return "Erro: 'lat' e 'lng' são obrigatórios e devem ser números."

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
        return "Não encontrei nenhuma célula nessa região. Quer que eu procure em outro endereço?"

    lines = [f"Encontrei {len(cells)} célula(s) perto:\n"]
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
            parts.append(f"{dist:.1f} km daqui")
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
