"""Compile i18n/*.ts to i18n/*.qm without Qt's lrelease (plain Python, no dependencies).

Writes the same file layout as lrelease: a hash table of (source text + comment) pointing to
message records that hold the translation, source text and context. Plural forms are not
supported - the plugin's messages use "{count}" placeholders instead of %n.
"""
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MODULE = "ekonomiska_kartan"
I18N_DIR = Path(__file__).resolve().parent.parent / MODULE / "i18n"

MAGIC = bytes(
    [0x3C, 0xB8, 0x64, 0x18, 0xCA, 0xEF, 0x9C, 0x95, 0xCD, 0x21, 0x1C, 0xBF, 0x60, 0xA1, 0xBD, 0xDD]
)
TAG_END, TAG_TRANSLATION, TAG_SOURCE, TAG_CONTEXT, TAG_COMMENT = 0x01, 0x03, 0x06, 0x07, 0x08
BLOCK_HASHES, BLOCK_MESSAGES = 0x42, 0x69
UNUSABLE = ("unfinished", "obsolete", "vanished")


def elf_hash(data):
    h = 0
    for byte in data:
        h = ((h << 4) + byte) & 0xFFFFFFFF
        g = h & 0xF0000000
        if g:
            h ^= g >> 24
        h &= ~g & 0xFFFFFFFF
    return h or 1


def read_ts(path):
    """[(context, source, comment, translation)] for every finished, non-empty message."""
    out = []
    for context in ET.parse(path).getroot().iter("context"):
        name = context.findtext("name") or ""
        for message in context.iter("message"):
            translation = message.find("translation")
            if translation is None or translation.get("type") in UNUSABLE:
                continue
            text = translation.text or ""
            if text:
                source = message.findtext("source") or ""
                out.append((name, source, message.findtext("comment") or "", text))
    return out


def _bytes(value):
    raw = value.encode("utf-8")
    return struct.pack(">I", len(raw)) + raw


def compile_messages(messages):
    """The .qm file content for [(context, source, comment, translation)]."""
    records = []  # (hash, offset) and the message data, in one pass
    data = bytearray()
    for context, source, comment, translation in messages:
        offset = len(data)
        raw = translation.encode("utf-16-be")
        data += bytes([TAG_TRANSLATION]) + struct.pack(">I", len(raw)) + raw
        data += bytes([TAG_SOURCE]) + _bytes(source)
        data += bytes([TAG_CONTEXT]) + _bytes(context)
        data += bytes([TAG_COMMENT]) + _bytes(comment)
        data += bytes([TAG_END])
        records.append((elf_hash((source + comment).encode("utf-8")), offset))
    hashes = b"".join(struct.pack(">II", h, o) for h, o in sorted(records))
    return (
        MAGIC
        + bytes([BLOCK_HASHES]) + struct.pack(">I", len(hashes)) + hashes
        + bytes([BLOCK_MESSAGES]) + struct.pack(">I", len(data)) + bytes(data)
    )


def compile_ts(ts_path):
    return compile_messages(read_ts(ts_path))


def main():
    for ts in sorted(I18N_DIR.glob("*.ts")):
        target = ts.with_suffix(".qm")
        target.write_bytes(compile_ts(ts))
        print(f"Wrote {target}")


if __name__ == "__main__":
    sys.exit(main())
