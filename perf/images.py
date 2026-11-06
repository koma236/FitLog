"""Deterministic RGB PNGs and an independent bounded PNG pixel oracle."""
import hashlib
import random
import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def image_fixture(size):
    if size not in {1, 147, 590, 1320}:
        raise ValueError("unknown fixed image size")
    rgb = random.Random(55).randbytes(size * size * 3)
    rows = b"".join(b"\0" + rgb[y * size * 3:(y + 1) * size * 3] for y in range(size))
    raw = (SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))
    return raw, hashlib.sha256(rgb).hexdigest()


def pixels(raw):
    if len(raw) > 5 * 1024 * 1024 or not raw.startswith(SIGNATURE):
        raise ValueError("invalid PNG")
    offset, compressed, ended, width, height = 8, bytearray(), False, 0, 0
    while offset + 12 <= len(raw):
        size = struct.unpack(">I", raw[offset:offset + 4])[0]
        kind = raw[offset + 4:offset + 8]
        data = raw[offset + 8:offset + 8 + size]
        if offset + size + 12 > len(raw) or zlib.crc32(kind + data) != struct.unpack(
                ">I", raw[offset + 8 + size:offset + 12 + size])[0]:
            raise ValueError("invalid PNG chunk")
        if kind == b"IHDR":
            width, height, depth, color, comp, filt, interlace = struct.unpack(">IIBBBBB", data)
            if (not 1 <= width <= 1320 or not 1 <= height <= 1320
                    or (depth, color, comp, filt, interlace) != (8, 2, 0, 0, 0)):
                raise ValueError("unexpected PNG format")
        elif kind == b"IDAT":
            compressed.extend(data)
        elif kind == b"IEND":
            ended = True
        offset += size + 12
    if not ended or not width or not height:
        raise ValueError("incomplete PNG")
    cap = height * (width * 3 + 1)
    data = zlib.decompressobj().decompress(bytes(compressed), cap + 1)
    if len(data) != cap:
        raise ValueError("unexpected PNG decoded size")
    stride, previous, output = width * 3, bytearray(width * 3), bytearray()
    for y in range(height):
        start = y * (stride + 1)
        kind = data[start]
        row = bytearray(data[start + 1:start + 1 + stride])
        if kind > 4:
            raise ValueError("invalid PNG row filter")
        for x in range(stride):
            a, b, c = row[x - 3] if x >= 3 else 0, previous[x], previous[x - 3] if x >= 3 else 0
            if kind == 0:
                predictor = 0
            elif kind == 1:
                predictor = a
            elif kind == 2:
                predictor = b
            elif kind == 3:
                predictor = (a + b) // 2
            else:
                p = a + b - c
                distances = (abs(p - a), abs(p - b), abs(p - c))
                predictor = (a, b, c)[distances.index(min(distances))]
            row[x] = (row[x] + predictor) & 255
        output.extend(row)
        previous = row
    return width, height, bytes(output)
