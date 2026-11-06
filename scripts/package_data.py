#!/usr/bin/env python3
"""Package OCR candidates, explicit visual checks and complete input coverage."""
import argparse
import csv
import gzip
import hashlib
import json
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path

from extract_tables import FACTORS


def tonnes(value, unit):
    return str(Decimal(value) * Decimal(str(FACTORS[unit]))) if value != '' and unit in FACTORS else ''


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields=None):
    rows = list(rows)
    fields = fields or list(rows[0])
    with Path(path).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def geography(name):
    name = name.strip()
    if any(s in name for s in ['自治区', '省', '全省']):
        return '', 'province'
    if any(s in name for s in ['地区', '自治州', '大理州', '全州']):
        return '', 'prefecture'
    if any(s in name for s in ['社区', '街道', '乡', '镇', '村']):
        return '', 'subcounty'
    m = re.match(r'^(.{1,18}?(?:自治县|自治旗|县|旗|区))', name)
    if m:
        return m.group(1), 'county_or_district_name'
    if name.endswith('市'):
        return name, 'city_level_unresolved'
    return '', 'unresolved'


def package(manifest_file, candidate_dir, ocr_dir, repo):
    repo = Path(repo)
    data = repo / 'data'
    manifest = json.loads(Path(manifest_file).read_text())
    by_id = {r['id']: r for r in manifest}
    rows = read_csv(Path(candidate_dir) / 'fertilizer_candidates.csv')
    exclusion_file = data / 'cell_exclusions.csv'
    exclusions = {(r['source_id'], r['year'], r['product_label']) for r in read_csv(exclusion_file)} if exclusion_file.exists() else set()
    rows = [r for r in rows if (r['source_id'], r['year'], r['product_label']) not in exclusions]
    metadata_file = data / 'source_metadata_overrides.csv'
    metadata = {r['source_id']: r for r in read_csv(metadata_file)} if metadata_file.exists() else {}
    geography_file = data / 'source_geography_overrides.csv'
    geo_overrides = {r['source_id']: r for r in read_csv(geography_file)} if geography_file.exists() else {}
    checked = read_csv(data / 'reviewed_cells.csv')
    reviewed = {(r['source_id'], r['year'], r['product_label']): r for r in checked}
    additions = ['record_id', 'county_raw', 'geography_level', 'quantity_ocr', 'value_status',
                 'review_note', 'metadata_source_id', 'printed_page']
    fields = list(rows[0]) + [k for k in additions if k not in rows[0]]
    present = set()
    for r in rows:
        r['county_raw'], r['geography_level'] = geography(r['source_location'])
        if r['source_id'] in geo_overrides:
            g = geo_overrides[r['source_id']]
            r['county_raw'], r['geography_level'] = g['county_raw'], g['geography_level']
        r['quantity_ocr'] = r['quantity']
        r['value_status'] = ('reported_ocr' if r['quantity'] != '' else
                             'unresolved_ocr' if any(s in r['review_flags'] for s in ['merged_numeric', 'long_digit_sequence']) else
                             'source_missing_symbol')
        key = r['source_id'], r['year'], r['product_label']
        present.add(key)
        if r['source_id'] in metadata:
            v = metadata[r['source_id']]
            r.update(unit=v['unit'], measurement_basis=v['basis'], measure_type=v['measure'],
                     review_note=v['note'], metadata_source_id=r['source_id'])
            r['quantity_tonnes'] = tonnes(r['quantity'], r['unit'])
            flags = [f for f in r['review_flags'].split(';') if f not in ['unit_not_resolved', 'measure_not_resolved']]
            r['review_flags'] = ';'.join(flags + ['metadata_visually_checked'])
        if key in reviewed:
            v = reviewed[key]
            r.update(quantity=v['quantity'], unit=v['unit'], measurement_basis=v['basis'],
                     measure_type=v['measure'], review_status=v['review_status'],
                     review_note=v['review_note'], metadata_source_id=v['metadata_source_id'],
                     printed_page=v['printed_page'], value_status=v['value_status'], review_flags='')
            r['quantity_tonnes'] = tonnes(v['quantity'], v['unit'])
        r['record_id'] = 'cell_' + hashlib.sha256((str(key) + r['value_bbox']).encode()).hexdigest()[:16]
    for key, v in reviewed.items():
        if key in present:
            continue
        m = by_id[v['source_id']]
        r = {k: '' for k in fields}
        r.update(source_id=v['source_id'], province=v['province'], source_location=v['county_raw'],
                 county_raw=v['county_raw'], geography_level='county_or_district_name', year=v['year'],
                 fertilizer_group=v['fertilizer_group'], product_label=v['product_label'],
                 quantity_raw=v['quantity'], quantity=v['quantity'], unit=v['unit'],
                 quantity_tonnes=tonnes(v['quantity'], v['unit']),
                 measurement_basis=v['basis'], measure_type=v['measure'], source_path=m['source_path'],
                 table_orientation='years_in_rows', review_status=v['review_status'],
                 review_note=v['review_note'], metadata_source_id=v['metadata_source_id'],
                 printed_page=v['printed_page'], value_status=v['value_status'])
        r['record_id'] = 'cell_' + hashlib.sha256(str(key).encode()).hexdigest()[:16]
        rows.append(r)
    rows.sort(key=lambda r: (r['province'], r['source_location'], int(r['year']), r['fertilizer_group'], r['product_label'], r['source_id']))
    write_csv(data / 'annual_fertilizer.csv', rows, fields)
    coverage = read_csv(Path(candidate_dir) / 'image_coverage.csv')
    write_csv(data / 'image_coverage.csv', coverage)
    # Keep the unmodified machine stage separate from subsequent explicit checks.
    write_csv(data / 'fertilizer_candidates.csv', read_csv(Path(candidate_dir) / 'fertilizer_candidates.csv'))
    ocr_observations = 0
    empty_ocr = []
    with gzip.open(repo / 'ocr' / 'observations.jsonl.gz', 'wt', encoding='utf-8') as out:
        for m in manifest:
            p = Path(ocr_dir) / (m['id'] + '.json')
            if not p.exists():
                raise ValueError('OCR result missing: ' + m['id'])
            record = json.loads(p.read_text())
            if record.get('status') != 'ok':
                raise ValueError('OCR failed: ' + m['id'])
            ocr_observations += len(record.get('observations', []))
            if not record.get('observations'):
                empty_ocr.append(m['id'])
            record['source_path'] = m['source_path']
            out.write(json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n')
    status = Counter(r['review_status'] for r in rows)
    summary = dict(input_images=len(manifest), unique_input_images=len({r['sha256'] for r in manifest}),
                   ocr_success=len(manifest), rows=len(rows), numeric_rows=sum(r['quantity'] != '' for r in rows),
                   ocr_observations=ocr_observations, ocr_empty_source_ids=empty_ocr,
                   source_directories=len({str(Path(r['source_path']).parent) for r in manifest}),
                   extracted_source_directories=len({(r['province'], r['source_location']) for r in rows}),
                   extracted_county_labels=len({(r['province'], r['county_raw']) for r in rows if r['county_raw'] and r['geography_level'] == 'county_or_district_name'}),
                   fertilizer_groups=dict(Counter(r['fertilizer_group'] for r in rows)),
                   review_status=dict(status), unknown_unit_rows=sum(not r['unit'] for r in rows),
                   unknown_basis_rows=sum(r['measurement_basis'] == 'unknown' for r in rows),
                   image_coverage_status=dict(Counter(r['status'] for r in coverage)),
                   year_min=min(int(r['year']) for r in rows), year_max=max(int(r['year']) for r in rows),
                   treatment_data_supplied=False, causal_estimates_computed=False)
    (data / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    assert len({r['record_id'] for r in rows}) == len(rows), 'Duplicate cell identifiers'
    assert all(r['quantity'] == '' or Decimal(r['quantity']).is_finite() for r in rows)
    assert all(r['fertilizer_group'] in ['N', 'P', 'K', 'compound'] for r in rows)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest_json')
    p.add_argument('candidate_dir')
    p.add_argument('ocr_dir')
    p.add_argument('repo_dir')
    a = p.parse_args()
    package(a.manifest_json, a.candidate_dir, a.ocr_dir, a.repo_dir)
