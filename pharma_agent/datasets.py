"""Prepare validated canonical datasets from legacy, long-table and matrix inputs."""
import hashlib
from imports import long_table,matrix,make_metadata,read_tables
from assays import profile
def prepare(raw,record=None,raw_name='RAW DATA.csv',record_name='',config=None):
    from analysis import parse_raw,parse_record,parse_instrument_background
    config=config or {}
    if not isinstance(config,dict) or any(not isinstance(config.get(k,{}),dict) for k in ('raw','record')):raise ValueError('导入配置及raw/record映射必须为对象。')
    raw_cfg=config.get('raw',{});record_cfg=config.get('record',{})
    # Table adapters are explicit and deterministic; the old protocol adapter
    # remains available without converting company/example answers into evidence.
    legacy=False
    if record and record_name.lower().endswith('.xlsx') and not record_cfg.get('columns'):
        tables,_=read_tables(record,record_name)
        legacy=any(name.lower()=='protocol' and any('Plate Map' in str(v) for row in rows for v in row if v is not None) for name,rows in tables.items())
    background=None;date='未提供';import_info={}
    if legacy:
        meta=parse_record(record);design=meta['design']
        try:values,source=matrix(raw,raw_name,raw_cfg)
        except ValueError:
            parsed=long_table(raw,raw_name,raw_cfg);values=parsed['values'];source=parsed['sheet']
        if raw_name.lower().endswith('.csv'):
            try:_,date=parse_raw(raw);background=parse_instrument_background(raw)
            except ValueError:pass
        import_info={'layout':'legacy_protocol','raw_sheet':source,'record_sheet':'protocol','mapping':{},'conversions':['nM→nM']}
    elif record:
        record_parsed=long_table(record,record_name,record_cfg,require_value=False,require_design=True)
        try:
            parsed=long_table(raw,raw_name,raw_cfg);values=parsed['values'];source=parsed['sheet']
        except ValueError as long_error:
            try:values,source=matrix(raw,raw_name,raw_cfg)
            except ValueError:raise long_error
        design=record_parsed['design'];meta=record_parsed['metadata']
        # Pairing requires explicit physical well identifiers, never row order.
        if any(d['well'].startswith('row-') for d in design):raise ValueError('双文件关联必须在设计表中提供孔位，不能按行号猜测对应关系。')
        import_info={'layout':'paired_tables','raw_sheet':source,'record_sheet':record_parsed['sheet'],'mapping':record_parsed['mapping'],'conversions':record_parsed['conversions']}
    else:
        parsed=long_table(raw,raw_name,raw_cfg,require_design=True)
        values=parsed['values'];design=parsed['design'];meta=parsed['metadata']
        import_info={'layout':'combined_long','raw_sheet':parsed['sheet'],'record_sheet':None,'mapping':parsed['mapping'],'conversions':parsed['conversions']}
    missing=[d['well'] for d in design if d['well'] not in values]
    if missing:raise ValueError('设计孔缺少原始数据：'+', '.join(missing))
    if len(design)>5000:raise ValueError('每批次最多5000条观测。')
    samples=sorted({d['sample'] for d in design if d['role']=='sample'})
    if not samples:raise ValueError('没有样品观测。')
    if len(samples)>48:raise ValueError('每批次最多48个样品；请分批上传。')
    original_hash=hashlib.sha256(raw).hexdigest();record_hash=hashlib.sha256(record).hexdigest() if record else None
    return {'metadata':meta,'samples':samples,'well_count':len(values),'date':date,'values':values,'instrument_background':background,'import_info':import_info,'raw_sha256':original_hash,'record_sha256':record_hash}
def preview(raw,record=None,raw_name='RAW DATA.csv',record_name='',config=None,options=None):
    d=prepare(raw,record,raw_name,record_name,config)
    result={k:v for k,v in d.items() if k not in ('values','instrument_background')}
    result['assay']=profile(options)
    return result
