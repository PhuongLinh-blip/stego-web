def hex_rows(raw, limit=4096):
    rows = []
    for offset in range(0, min(len(raw), limit), 16):
        block = raw[offset:offset+16]
        rows.append((f'{offset:08X}', block.hex(' ').upper(), ''.join(chr(b) if 32 <= b <= 126 else '.' for b in block)))
    return rows
