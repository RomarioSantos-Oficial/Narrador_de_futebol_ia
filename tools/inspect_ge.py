"""Diagnóstico manual de uma página GE; não altera o overlay nem inicia polling.

Lê somente valores JSON de window.trv2, sem executar JavaScript. A estrutura
é interna ao site e pode mudar. O resultado local não concede licença de uso.
"""

import argparse
import json
import re
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


MAX_BYTES = 4 * 1024 * 1024


def validate_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "ge.globo.com"
            or parsed.port not in (None, 443) or parsed.username or parsed.password
            or "/jogo/" not in parsed.path or not parsed.path.endswith(".ghtml")):
        raise ValueError("Informe uma URL HTTPS de partida em ge.globo.com.")
    return url


def parse_page(html):
    marker = re.search(r"window\.trv2\s*=\s*\{", html)
    if marker is None:
        raise ValueError("Dados window.trv2 ausentes; a estrutura da página pode ter mudado.")
    end = html.find("</script>", marker.end())
    if end < 0:
        raise ValueError("Configuração da página incompleta.")
    block = html[marker.end():end]

    def read(key, expected, required=False):
        match = re.search(r"(?m)^\s*" + re.escape(key)
                          + r":\s*(?:Array\.from\(\s*)?", block)
        if match is None:
            if required:
                raise ValueError(f"Campo obrigatório ausente: {key}.")
            return None
        value, _ = json.JSONDecoder().raw_decode(block[match.end():])
        if value is None:
            if required:
                raise ValueError(f"Campo obrigatório nulo: {key}.")
            return None
        if not isinstance(value, expected):
            raise ValueError(f"Formato inesperado em {key}.")
        return value

    transmission = read("transmission", dict, required=True)
    match = transmission.get("match")
    if not isinstance(match, dict) or not match.get("id"):
        raise ValueError("Identificação da partida ausente.")
    plays = read("plays", list, required=True)
    events = []
    for play in plays:
        if not isinstance(play, dict) or not play.get("id"):
            raise ValueError("Lance sem identificação válida.")
        body = play.get("body") or {}
        blocks = body.get("blocks", [])
        # Apenas texto: ignora vídeos, imagens, embeds e marcação executável.
        paragraphs = [item["text"] for item in blocks
                      if isinstance(item, dict) and isinstance(item.get("text"), str)
                      and item.get("type") != "atomic"]
        events.append({
            "id": play["id"], "createdAt": play.get("createdAt"),
            "moment": play.get("moment"), "period": play.get("period"),
            "type": play.get("playType"), "title": play.get("title"),
            "details": play.get("details"), "text": "\n".join(paragraphs),
        })
    field = read("theSportsField", dict) or {}
    # Não exporta parâmetros do widget contratado pelo portal.
    field_host = urlsplit(field.get("url") or "").hostname
    return {
        "schemaVersion": 1,
        "mode": "manual_diagnostic_snapshot",
        "transmission": transmission,
        "statistics": read("statistics", dict),
        "matchHistory": read("matchHistory", dict),
        "events": events,
        "field": {"embeddedWidgetHost": field_host,
                  "trackingDataExtracted": False},
        "latestEventCreatedAt": max((e["createdAt"] for e in events
                                     if isinstance(e["createdAt"], str)), default=None),
        "notes": [
            "Uma leitura isolada; não confirma atualização contínua ou latência.",
            "currentTime é o valor bruto da página, não um relógio ao vivo validado.",
            "Dados ausentes permanecem ausentes; zero fornecido pela fonte é preservado.",
            "Eventos incluem pré-jogo e resumos; não são todos ações novas da partida.",
            "Texto editorial é preservado apenas neste diagnóstico local, sem reprodução automática.",
            "Nenhuma posição de bola ou posse por jogador foi extraída do widget externo.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="URL pública da partida; realiza uma única consulta.")
    source.add_argument("--html", type=Path, help="HTML já salvo, sem acesso à internet.")
    parser.add_argument("--output", type=Path, required=True, help="Arquivo JSON de diagnóstico.")
    args = parser.parse_args()
    try:
        if args.url:
            validate_url(args.url)
            request = Request(args.url, headers={"User-Agent": "FutebolLiveOverlay-Diagnostic/1.0"})
            with urlopen(request, timeout=20, context=ssl.create_default_context()) as response:
                validate_url(response.url)
                raw = response.read(MAX_BYTES + 1)
            source_info = {"url": args.url, "fetchedAt": datetime.now(timezone.utc).isoformat()}
        else:
            with args.html.open("rb") as saved:
                raw = saved.read(MAX_BYTES + 1)
            source_info = {"file": str(args.html.resolve()), "fetchedAt": None}
        if len(raw) > MAX_BYTES:
            raise ValueError("Página maior que o limite de 4 MiB.")
        snapshot = parse_page(raw.decode("utf-8"))
        snapshot["source"] = source_info
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        match = snapshot["transmission"]["match"]
        squads = match.get("squads") or {}
        print(f"Partida GE: {match['id']}; registros: {len(snapshot['events'])}")
        for side in ("homeTeam", "awayTeam"):
            squad = squads.get(side) or {}
            name = (match.get(side) or {}).get("popularName", side)
            print(f"{name}: {len(squad.get('lineUp') or [])} titulares; "
                  f"{len(squad.get('bench') or [])} reservas")
        print(f"Diagnostico salvo: {args.output}")
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        parser.exit(1, f"Diagnóstico não concluído: {exc}\n")


if __name__ == "__main__":
    main()
