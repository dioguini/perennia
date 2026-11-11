"""Ler XML de ficheiros que vêm de fora (GPX, ZWO, TCX…) sem se expor.

O XML pode trazer uma «DTD» com entidades que se multiplicam (a «bomba» de entidades) ou que
leem ficheiros. Nenhum dos formatos que a Perennia lê precisa disso, por isso um ficheiro com
`<!DOCTYPE` ou `<!ENTITY` é simplesmente recusado. O tamanho também tem um limite.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

MAX_BYTES = 100 * 1024 * 1024        # 100 MB: um GPX de um dia inteiro tem poucos MB


class UnsafeXML(ValueError):
    pass


def _check(data: bytes) -> bytes:
    if len(data) > MAX_BYTES:
        raise UnsafeXML("ficheiro XML grande de mais")
    head = data.lower()
    # UTF-16 também: tiram-se os zeros antes de procurar
    flat = head.replace(b"\x00", b"")
    if b"<!doctype" in flat or b"<!entity" in flat:
        raise UnsafeXML("ficheiro XML com DTD/entidades: recusado por segurança")
    return data


def fromstring(data: bytes | str) -> ET.Element:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return ET.fromstring(_check(raw))


def parse(path: str | Path) -> ET.ElementTree:
    p = Path(path)
    if p.stat().st_size > MAX_BYTES:
        raise UnsafeXML("ficheiro XML grande de mais")
    return ET.ElementTree(fromstring(p.read_bytes()))
