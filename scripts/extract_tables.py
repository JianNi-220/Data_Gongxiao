#!/usr/bin/env python3
"""Conservative table-only annual fertilizer candidates from Vision OCR boxes.

All machine extracted cells remain unreviewed. Narrative observations are never
used as quantity cells. No imputation, fertilizer summation, or nutrient conversion.
"""
import argparse
import csv
import json
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

PRODUCTS = [
    ('compound', r'复[合混]肥(?:料)?|混合肥料|三元复合肥|二元复合肥|磷酸[一二]铵'),
    ('N', r'固体氮肥|氮肥|氧肥|氨水|尿素|碳酸氢铵|碳铵|硫酸铵|硫铵|硝酸铵|硝铵|氯化铵|液氨|硝酸钙|石灰氮'),
    ('P', r'磷肥|过磷酸钙|普钙|重过磷酸钙|钙镁磷肥|钙镁磷|磷矿粉|磷粉'),
    ('K', r'钾肥|氯化钾|硫酸钾|钾盐'),
]
PRODUCT_RE = re.compile('|'.join('(?P<%s>%s)' % x for x in PRODUCTS))
YEAR_RE = re.compile(r'(?:19\d\d|20[0-2]\d)')
NUMBER_RE = re.compile(r'[+-]?(?:\d{1,3}(?:[,，]\d{3})+|\d+)(?:[.．]\d+)?')
MISSING = {'-', '—', '－', '–', '…', '...', '/', '／', '·', '..', '〃'}
UNIT_RE = re.compile(r'万公斤|万千克|万市担|万市斤|万吨|万担|万斤|千吨|千担|百吨|百担|百公斤|市担|公担|公斤|千克|市斤|吨|担|斤')
FACTORS = {'万公斤':10, '万千克':10, '万市担':500, '万市斤':5, '万斤':5, '百吨':100, '百担':5, '万吨':10000, '千吨':1000, '吨':1, '万担':500, '千担':50, '担':.05, '市担':.05,
           '公担':.1, '百公斤':.1, '公斤':.001, '千克':.001, '斤':.0005, '市斤':.0005}
FIELDS = ['source_id','province','source_location','year','fertilizer_group','product_label',
          'quantity_raw','quantity','unit','quantity_tonnes','measurement_basis','measure_type',
          'source_path','table_orientation','year_bbox','header_bbox','value_bbox','ocr_confidence',
          'review_status','review_flags']


def norm(text):
    return unicodedata.normalize('NFKC', text).strip()


def box(obs):
    b=obs['bbox']
    return [b['x'], b['y'], b['width'], b['height']]


def center(obs):
    x,y,w,h=box(obs)
    return x+w/2,y+h/2


def split_numeric(obs):
    """Only numeric cells/lines; strip grid punctuation without guessing digits."""
    s=norm(obs['text'])
    if re.fullmatch(r'\d{1,3}(?:\s+\d{3})+(?:\.\d+)?',s) and box(obs)[2]<=max(.04,box(obs)[3]*3):
        return [dict(obs,text=re.sub(r'\s+','',s),original_text=obs['text'],token_approximate=False,grouped_thousands=True)]
    if NUMBER_RE.fullmatch(s) or s in MISSING:
        return [dict(obs, token_approximate=False)]
    pieces=list(NUMBER_RE.finditer(s))
    residual=NUMBER_RE.sub('',s)
    if pieces and not re.sub(r'[\s|｜()（）\[\]【】]', '', residual):
        x,y,w,h=box(obs)
        chars=obs.get('characters',[])
        out=[]
        for m in pieces:
            exact=chars[m.start():m.end()] if len(chars)==len(s) else []
            if exact:
                boxes=[c['bbox'] for c in exact]
                xx=min(b['x'] for b in boxes); yy=min(b['y'] for b in boxes)
                rr=max(b['x']+b['width'] for b in boxes);tt=max(b['y']+b['height'] for b in boxes)
                b={'x':xx,'y':yy,'width':rr-xx,'height':tt-yy}
            else:
                b={'x':x+w*m.start()/len(s),'y':y,'width':w*(m.end()-m.start())/len(s),'height':h}
            out.append(dict(obs,text=m.group(),bbox=b,token_approximate=not bool(exact),numeric_punctuation_removed=True))
        return out
    return []


def quantities(observations):
    out=[]
    for o in observations:
        out.extend(split_numeric(o))
    return out


def numeric(s):
    s=norm(s)
    if s in MISSING:
        return ''
    if not NUMBER_RE.fullmatch(s):
        return None
    try:
        return str(Decimal(s.replace(',','').replace('，','')))
    except InvalidOperation:
        return None


def products(observations):
    out=[]
    # OCR often splits headers across cell borders (e.g. 氨 / 水磷 / 肥钾 / 肥).
    # Stitch short observations on one baseline, retaining each character's geometry.
    short=[o for o in observations if 0<len(norm(o['text']).replace(' ',''))<=22
           and not any(c in norm(o['text']) for c in '。；！？')
           and not NUMBER_RE.fullmatch(norm(o['text']))]
    bands=[]
    for o in sorted(short,key=lambda o:-center(o)[1]):
        matches=[g for g in bands if abs(center(o)[1]-statistics.median(center(z)[1] for z in g))<.012]
        if matches: matches[0].append(o)
        else: bands.append([o])
    for band in bands:
        band=sorted(band,key=lambda o:box(o)[0])
        segments=[]; current=[]
        for o in band:
            if current and box(o)[0]-(box(current[-1])[0]+box(current[-1])[2])>.07:
                segments.append(current);current=[]
            current.append(o)
        if current: segments.append(current)
        for segment in segments:
            chars=[]
            for o in segment:
                text=norm(o['text']).replace(' ','')
                x,y,w,h=box(o)
                geometry=o.get('characters',[])
                if geometry and ''.join(c['text'] for c in geometry)==text:
                    chars.extend((c['text'], c['bbox'], o.get('confidence',0)) for c in geometry)
                else:
                    chars.extend((c,{'x':x+w*i/len(text),'y':y,'width':w/len(text),'height':h},o.get('confidence',0)) for i,c in enumerate(text))
            text=''.join(c[0] for c in chars)
            for m in PRODUCT_RE.finditer(text):
                cs=chars[m.start():m.end()]
                x=min(c[1]['x'] for c in cs);y=min(c[1]['y'] for c in cs)
                r=max(c[1]['x']+c[1]['width'] for c in cs);t=max(c[1]['y']+c[1]['height'] for c in cs)
                out.append({'text':m.group(),'group':m.lastgroup,'confidence':min(c[2] for c in cs),
                            'bbox':{'x':x,'y':y,'width':r-x,'height':t-y},'header_approximate':True})
    for o in observations:
        s=norm(o['text']).replace(' ','')
        # Titles and prose name products too; only short label observations qualify.
        if len(s)>22 or any(p in s for p in ['。','；','！','？','统计表','一览表']):
            continue
        for m in PRODUCT_RE.finditer(s):
            x,y,w,h=box(o)
            out.append(dict(o,text=m.group(),group=m.lastgroup,
                            bbox={'x':x+w*m.start()/max(1,len(s)),'y':y,
                                  'width':w*(m.end()-m.start())/max(1,len(s)),'height':h},
                            header_approximate=(m.start()!=0 or m.end()!=len(s))))
    return out


def cluster_x(items, tolerance=.025):
    groups=[]
    for o in sorted(items,key=lambda o:center(o)[0]):
        x=center(o)[0]
        matching=[g for g in groups if abs(x-statistics.median(center(z)[0] for z in g))<=tolerance]
        if matching: matching[0].append(o)
        else: groups.append([o])
    return groups


def annual_year_columns(years):
    """Do not carry one table's fertilizer headers into the next table below it."""
    out=[]
    for g in cluster_x(years):
        ordered=sorted(g,key=lambda o:-center(o)[1])
        gaps=[center(a)[1]-center(b)[1] for a,b in zip(ordered,ordered[1:])]
        maxgap=max(.065,statistics.median(gaps)*2.8) if gaps else .065
        run=[]
        for o in ordered:
            if run and (int(norm(o['text']))<=int(norm(run[-1]['text'])) or center(run[-1])[1]-center(o)[1]>maxgap):
                if len(set(norm(z['text']) for z in run))>=3: out.append(run)
                run=[]
            run.append(o)
        if len(set(norm(z['text']) for z in run))>=3: out.append(run)
    return out


def non_quantity_table(observations,top,left,right):
    text=' '.join(norm(o['text']) for o in observations
        if left-.025<=center(o)[0]<=right+.025 and top-.01<=center(o)[1]<=min(.99,top+.24))
    return bool(re.search(r'比重|比率|比例|构成.*%|价格表|销售价格|销售价|收购价格|单价|零售价|批发价|元\s*[/／]\s*(?:吨|担|公斤|千克)',text))


def context(header, observations, top, left, right):
    htxt=' '.join(o['text'] for o in observations
                  if left <= center(o)[0] <= right and top-.015 <= center(o)[1] <= min(.99,top+.24))
    unit=''
    matches=UNIT_RE.findall(htxt)
    if matches:
        # Money-value and price observations are not physical quantity units.
        # Resolve using the closest heading covering this product column.
        hx=center(header)[0]
        unit_obs=[o for o in observations if UNIT_RE.search(o['text']) and top-.015<=center(o)[1]<=min(.99,top+.24)
                  and box(o)[0]-.025<=hx<=box(o)[0]+box(o)[2]+.025]
        unit_obs.sort(key=lambda o:(abs(center(o)[1]-center(header)[1]),box(o)[2]))
        local=UNIT_RE.findall(unit_obs[0]['text']) if unit_obs else []
        if local and len(set(local))==1 and not any(t in unit_obs[0]['text'] for t in ['元','价格','单价','%','％']):
            unit=local[0]
        # Conflicting unit labels cannot be resolved from one page-level context.
        unique=set(matches)
        if not unit and len(unique)==1 and not any(t in htxt for t in ['元','价格','单价','%','％']): unit=matches[0]
    basis='nutrient' if any(s in htxt for s in ['折纯','纯量','有效成分','养分量']) else 'unknown'
    if any(s in htxt for s in ['实物','实物量']): basis='physical'
    if any(s in htxt for s in ['标准吨','折标','标准肥']): basis='standard_equivalent'
    measure='unknown'
    if any(s in htxt for s in ['销售','售出','销出','销给','销量']): measure='sales'
    elif any(s in htxt for s in ['供应','供给','供销']): measure='supply'
    elif any(s in htxt for s in ['施用','使用量','用肥']): measure='use'
    elif any(s in htxt for s in ['购进','购入','收购']): measure='purchases'
    elif re.search(r'产量|生产量|生产统计表|化肥生产(?!资料)',htxt): measure='production'
    return unit,basis,measure


def make_record(meta, year, header, value, unit, basis, measure, orientation, flags):
    q=numeric(value['text'])
    if q is None: return None
    if value.get('token_approximate'): flags.append('numeric_line_split_geometry')
    if value.get('numeric_punctuation_removed'): flags.append('numeric_grid_punctuation_removed')
    if value.get('grouped_thousands'): flags.append('grouped_thousands_joined')
    if header.get('header_approximate'): flags.append('header_split_geometry')
    if header['text']=='氧肥': flags.append('possible_氮肥_header_ocr')
    if header['text'] in ['磷酸一铵','磷酸二铵']: flags.append('group_classification_from_chemistry')
    if unit=='': flags.append('unit_not_resolved')
    if basis=='unknown': flags.append('basis_not_explicit')
    if measure=='unknown': flags.append('measure_not_resolved')
    if q=='' and norm(value['text']) in MISSING: flags.append('source_missing_symbol')
    if value.get('merged_columns'):
        q=''; flags.append('merged_numeric_columns_unresolved')
    # Observed failures concatenate neighboring cells into 8–14 digit integers.
    # Keep their OCR text for review; this does not impose a true quantity limit.
    if q and re.fullmatch(r'\d{8,}', q):
        q=''; flags.append('long_digit_sequence_unresolved')
    if q and Decimal(q)<0: flags.append('negative_quantity')
    confidence=min(float(x.get('confidence',0)) for x in [year,header,value])
    if confidence<.9: flags.append('low_ocr_confidence')
    ton=''
    if q and unit in FACTORS:
        ton=str(Decimal(q)*Decimal(str(FACTORS[unit])))
    return dict(source_id=meta['id'],province=meta.get('province',''),source_location=meta.get('source_location',''),
        year=norm(year['text']),fertilizer_group=header['group'],product_label=header['text'],
        quantity_raw=value.get('original_text',value['text']),quantity=q,unit=unit,quantity_tonnes=ton,
        measurement_basis=basis,measure_type=measure,source_path=meta.get('source_path',meta.get('path','')),
        table_orientation=orientation,year_bbox=json.dumps(box(year)),header_bbox=json.dumps(box(header)),
        value_bbox=json.dumps(box(value)),ocr_confidence=round(confidence,4),review_status='ocr_candidate',
        review_flags=';'.join(sorted(set(flags))))


def extract_vertical(meta, observations, nums, headers):
    years=[o for o in nums if YEAR_RE.fullmatch(norm(o['text']))]
    yearcols=annual_year_columns(years)
    records=[]
    for gi, yearcol in enumerate(yearcols):
        yearcol=sorted(yearcol,key=lambda o:-center(o)[1])
        yearx=statistics.median(center(o)[0] for o in yearcol)
        top=max(center(o)[1] for o in yearcol)
        bottom=min(center(o)[1] for o in yearcol)
        # Four-digit quantities sometimes align; a year column must mostly be monotonic.
        vals=[int(norm(o['text'])) for o in yearcol]
        changes=[b-a for a,b in zip(vals,vals[1:])]
        if changes and max(sum(d>0 for d in changes),sum(d<0 for d in changes)) < .75*len(changes):
            continue
        axis_labels=[o for o in observations if any(w in norm(o['text']) for w in ['年','度','年份','年度'])
                     and top-.01<center(o)[1]<min(.99,top+.20)
                     and box(o)[0]-.04<=yearx<=box(o)[0]+box(o)[2]+.04]
        if not axis_labels: continue
        nextxs=[statistics.median(center(o)[0] for o in g) for g in yearcols if statistics.median(center(o)[0] for o in g)>yearx+.06]
        right=min(nextxs)-.025 if nextxs else 1.0
        label_candidates=[h for h in headers if yearx+.015<center(h)[0]<right and top-.003<center(h)[1]<min(.99,top+.22)]
        if not label_candidates: continue
        right=min(right,max(box(h)[0]+box(h)[2] for h in label_candidates)+.045)
        if non_quantity_table(observations,top,yearx,right): continue
        yheights=[box(o)[3] for o in yearcol]
        tolerance=max(.005,statistics.median(yheights)*.7)
        # The bottom-most label at a numeric column is the actual leaf header.
        hgroups=cluster_x(label_candidates,.028)
        leaves=[min(g,key=lambda h:center(h)[1]) for g in hgroups]
        for year in yearcol:
            y=center(year)[1]
            row=[n for n in nums if yearx+.018<center(n)[0]<right and abs(center(n)[1]-y)<=tolerance]
            for h in leaves:
                hx=center(h)[0]
                cand=sorted(row,key=lambda n:abs(center(n)[0]-hx))
                if not cand: continue
                value=cand[0]
                dist=abs(center(value)[0]-hx)
                # Wide header labels can cover a narrow centered quantity.
                if dist>max(.025,box(h)[2]*.70): continue
                # A numeric cell must be closer to this label than other leaf labels.
                if any(abs(center(value)[0]-center(oh)[0])+1e-5<dist for oh in leaves if oh is not h): continue
                crossed=[oh for oh in leaves if box(value)[0]+.003<center(oh)[0]<box(value)[0]+box(value)[2]-.003]
                if len(crossed)>1: value=dict(value,merged_columns=True)
                unit,basis,measure=context(h,observations,top,yearx-.035,right)
                flags=[]
                if len(cand)>1 and abs(center(cand[1])[0]-hx)-dist<.008: flags.append('ambiguous_column_match')
                r=make_record(meta,year,h,value,unit,basis,measure,'years_in_rows',flags)
                if r: records.append(r)
    return records


def extract_horizontal(meta, observations, nums, headers):
    years=[o for o in nums if YEAR_RE.fullmatch(norm(o['text']))]
    # At least three years share a header row, then product labels must lie below it.
    rows=[]
    for y in sorted(years,key=lambda o:-center(o)[1]):
        cy=center(y)[1]
        groups=[g for g in rows if abs(cy-statistics.median(center(z)[1] for z in g))<.016]
        if groups: groups[0].append(y)
        else: rows.append([y])
    records=[]
    for yearrow in rows:
        if len(set(norm(o['text']) for o in yearrow))<3: continue
        yearrow=sorted(yearrow,key=lambda o:center(o)[0])
        vals=[int(norm(o['text'])) for o in yearrow]
        if sum(b>a for a,b in zip(vals,vals[1:]))<.75*(len(vals)-1): continue
        top=statistics.median(center(o)[1] for o in yearrow)
        left=min(center(o)[0] for o in yearrow)
        if non_quantity_table(observations,top,0,1): continue
        right=max(center(o)[0] for o in yearrow)
        hs=[h for h in headers if center(h)[0]<left-.02 and .04<center(h)[1]<top-.025]
        for h in hs:
            hy=center(h)[1]
            row=[n for n in nums if left-.025<center(n)[0]<right+.04 and abs(center(n)[1]-hy)<max(.009,box(h)[3]*.65)]
            for year in yearrow:
                if not row: continue
                x=center(year)[0]
                value=min(row,key=lambda n:abs(center(n)[0]-x))
                if abs(center(value)[0]-x)>.026: continue
                unit,basis,measure=context(h,observations,top,.0,1.0)
                r=make_record(meta,year,h,value,unit,basis,measure,'years_in_columns',[])
                if r: records.append(r)
    return records


def extract(meta, page):
    if page.get('status')!='ok': return [],'ocr_error'
    observations=page.get('observations',[])
    nums=quantities(observations)
    headers=products(observations)
    if not headers: return [],'no_short_fertilizer_labels'
    records=extract_vertical(meta,observations,nums,headers)+extract_horizontal(meta,observations,nums,headers)
    seen=set(); unique=[]
    for r in records:
        key=(r['year'],r['product_label'],r['value_bbox'])
        if key not in seen: seen.add(key); unique.append(r)
    if unique: return unique,'annual_fertilizer_table_candidates'
    return [],'no_supported_annual_table_layout'


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('manifest',type=Path)
    ap.add_argument('ocr_dir',type=Path)
    ap.add_argument('output_dir',type=Path)
    ap.add_argument('--exclusions',type=Path,help='Manually reviewed CSV columns source_id,reason; preserves exclusions in coverage')
    a=ap.parse_args()
    exclusions={}
    if a.exclusions:
        with a.exclusions.open(encoding='utf-8-sig',newline='') as f:
            exclusions={r['source_id']:r['reason'] for r in csv.DictReader(f)}
    a.output_dir.mkdir(parents=True,exist_ok=True)
    allrows=[]; coverage=[]; seen_hashes={}
    for meta in json.loads(a.manifest.read_text()):
        p=a.ocr_dir/(meta['id']+'.json')
        if not p.exists(): rows=[]; reason='ocr_missing'
        else:
            rows,reason=extract(meta,json.loads(p.read_text()))
        if meta['id'] in exclusions:
            rows=[];reason='manual_exclusion:'+exclusions[meta['id']]
        sha=meta.get('sha256')
        if sha and sha in seen_hashes:
            rows=[];reason='exact_duplicate_image:'+seen_hashes[sha]
        elif sha: seen_hashes[sha]=meta['id']
        allrows.extend(rows)
        page=json.loads(p.read_text()) if p.exists() else {}
        num=quantities(page.get('observations',[]))
        years=[o for o in num if YEAR_RE.fullmatch(norm(o['text']))]
        max_years=max([len(g) for g in cluster_x(years)]+[0])
        if not rows and max_years>=3 and reason in {'no_short_fertilizer_labels','no_supported_annual_table_layout'}:
            reason='annual_table_header_or_layout_unresolved'
        coverage.append(dict(aligned_years_max=max_years,fertilizer_labels=len(products(page.get('observations',[]))),source_id=meta['id'],province=meta.get('province',''),source_location=meta.get('source_location',''),
                             source_path=meta.get('source_path',''),candidate_cells=len(rows),status=reason))
    for name,data,fields in [('fertilizer_candidates.csv',allrows,FIELDS),('image_coverage.csv',coverage,list(coverage[0]) if coverage else ['source_id','status'])]:
        with (a.output_dir/name).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(data)
    summary={'images':len(coverage),'candidate_cells':len(allrows),'images_with_candidates':sum(bool(c['candidate_cells']) for c in coverage),
             'status_counts':dict(Counter(c['status'] for c in coverage)),'fertilizer_group_counts':dict(Counter(r['fertilizer_group'] for r in allrows)),
             'machine_review_status':'All cells are ocr_candidate; not a verified analysis panel.'}
    (a.output_dir/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__': main()
