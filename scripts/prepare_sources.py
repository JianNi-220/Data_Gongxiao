#!/usr/bin/env python3
"""Extract PNG inputs and create the stable source manifest (Python stdlib only)."""
import argparse
import csv
import hashlib
import json
import struct
import zipfile
from pathlib import Path, PurePosixPath


def prepare(archive, raw_dir, manifest_file):
    rows = []
    raw_dir = Path(raw_dir).resolve()
    with zipfile.ZipFile(archive) as z:
        for info in sorted(z.infolist(), key=lambda i: i.filename):
            name = PurePosixPath(info.filename)
            if name.suffix.lower() != '.png' or '__MACOSX' in name.parts:
                continue
            if name.is_absolute() or '..' in name.parts:
                raise ValueError(f'Unsafe archive path: {name}')
            relative = PurePosixPath(*name.parts[1:]) if name.parts[0] == '供销志' else name
            target = raw_dir.joinpath(*relative.parts)
            data = z.read(info)  # zipfile verifies each entry's CRC.
            if data[:8] != b'\x89PNG\r\n\x1a\n':
                raise ValueError(f'PNG signature missing: {name}')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            width, height = struct.unpack('>II', data[16:24])
            parts = relative.parts
            rows.append(dict(id='img_' + hashlib.sha256(str(relative).encode()).hexdigest()[:16],
                             path=str(target), source_path=str(relative), province=parts[0],
                             source_location=parts[1] if len(parts) > 2 else relative.stem,
                             sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
                             width=width, height=height))
    manifest_file = Path(manifest_file)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    with manifest_file.with_suffix('.csv').open('w', encoding='utf-8-sig', newline='') as f:
        fields = [k for k in rows[0] if k != 'path'] if rows else ['id', 'source_path']
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows({k: row[k] for k in fields} for row in rows)
    print(json.dumps({'images': len(rows), 'unique_images': len({r['sha256'] for r in rows})}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive')
    p.add_argument('raw_dir')
    p.add_argument('manifest_json')
    a = p.parse_args()
    prepare(a.archive, a.raw_dir, a.manifest_json)
