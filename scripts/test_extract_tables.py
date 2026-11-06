#!/usr/bin/env python3
"""One runnable parser check: layout matching, zero/missing, prose rejection."""
from extract_tables import extract, numeric


def obs(text,x,y,w=.04,h=.02):
    return dict(text=text,confidence=.99,bbox=dict(x=x,y=y,width=w,height=h))

meta=dict(id='fixture',province='省',source_location='县',source_path='fixture.png')
page=dict(status='ok',observations=[obs('年度氮磷钾销售表',.05,.94,.5),obs('单位：吨',.7,.89,.1),
    obs('氮肥',.2,.84),obs('磷肥',.4,.84),obs('钾肥',.6,.84),obs('复合肥',.8,.84,.06)]+
    [obs(str(1970+i),.05,.75-i*.08) for i in range(3)]+
    [obs(str(v),x,.75-i*.08) for i,row in enumerate([[12,0,4,5],[20,1,5,6],[30,2,6,7]]) for x,v in zip([.2,.4,.6,.8],row)]+
    [obs('1971年氮肥销量达999吨。',.05,.38,.7)])
rows,reason=extract(meta,page)
assert reason=='annual_fertilizer_table_candidates'
assert len(rows)==12, rows
assert next(r for r in rows if r['year']=='1970' and r['fertilizer_group']=='P')['quantity']=='0'
assert not any(r['quantity']=='999' for r in rows)
assert all(r['review_status']=='ocr_candidate' for r in rows)
assert all(r['unit']=='吨' for r in rows)
assert numeric('-')=='' and numeric('0')=='0' and numeric('1,234.5')=='1234.5'
assert numeric('2O3') is None
prose=dict(status='ok',observations=[obs('1970年氮肥销量12吨',.1,.8,.7),obs('1971年磷肥销量15吨',.1,.7,.7),obs('1972年钾肥销量18吨',.1,.6,.7)])
assert extract(meta,prose)[0]==[]
# Rotated panel: years across columns and product labels in rows.
horizontal=dict(status='ok',observations=[obs('单位：吨',.05,.9,.1)]+
    [obs(str(1970+i),.3+i*.12,.8) for i in range(3)]+
    [obs('氮肥',.08,.65),obs('磷肥',.08,.55)]+
    [obs(str(10+i+j),.3+i*.12,y) for j,y in enumerate([.65,.55]) for i in range(3)])
assert len(extract(meta,horizontal)[0])==6
print('Table extraction checks passed')
# A price/% table cannot become quantity observations because it includes fertilizer labels.
from extract_tables import split_numeric
assert split_numeric(obs('1 056',.2,.5,.026))[0]['text']=='1056'
price=dict(page,observations=page['observations']+[obs('择年化肥销售价格表 元/吨',.1,.91,.6)])
assert extract(meta,price)[0]==[]
percent=dict(page,observations=page['observations']+[obs('化肥销售量比重表（%）',.1,.91,.6)])
assert extract(meta,percent)[0]==[]
print('Grouped thousands and non-quantity checks passed')
from extract_tables import make_record
long_value=make_record(meta,obs('1970',.05,.75),dict(obs('氮肥',.2,.84),group='N'),
                       obs('586119280',.2,.75),'吨','unknown','sales','years_in_rows',[])
assert long_value['quantity']=='' and long_value['quantity_raw']=='586119280'
assert 'long_digit_sequence_unresolved' in long_value['review_flags']
print('Unresolved merged integer check passed')
