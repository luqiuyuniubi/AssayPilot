"""Publish diverse synthetic formats, units, headers and assay directions."""
import csv,io,json,math,sys
from pathlib import Path
from openpyxl import Workbook
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'data'/'flexible';OUT.mkdir(exist_ok=True)
def rows(mode='inhibition'):
    out=[]
    for sample,mid in [('Candidate-A',5.),('Candidate-B',12.)]:
        for c in [.03,.1,.3,1,3,10,30,100,300]:
            decreasing=100+900/(1+(c/mid)**1.4)
            value=1100-decreasing if mode=='activation' else decreasing
            for factor in (.995,1.005):out.append({'sample':sample,'concentration':c/1000,'unit':'uM','value':value*factor,'role':'sample'})
    for role,value in [('high',1000),('low',100)]:
        for factor in (.995,1.005):out.append({'sample':role,'concentration':'','unit':'uM','value':value*factor,'role':role})
    return out
def main():
    for mode in ('inhibition','activation','viability','enzyme'):
        data=rows(mode);metadata={'title':'合成'+mode+'浓度响应','purpose':'实验目的：验证多格式、多单位和显式分析场景。'}
        (OUT/(mode+'.json')).write_text(json.dumps({'metadata':metadata,'measurements':data},indent=2),encoding='utf-8')
    data=rows();columns=list(data[0])
    for ext,delimiter in [('csv',','),('tsv','\t'),('txt',';')]:
        with (OUT/('inhibition.'+ext)).open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=columns,delimiter=delimiter);writer.writeheader();writer.writerows(data)
    for filename,mode,custom in [('activation.xlsx','activation',False),('custom-headers.xlsx','inhibition',True)]:
        wb=Workbook();ws=wb.active;ws.title='Measurements'
        ws.append(['Synthetic dataset; no real research input'])
        ws.append(['compound_code','dose_level','dose_units','sensor_reading','group_type'] if custom else columns)
        for row in rows(mode):ws.append([row[k] for k in columns])
        noise=wb.create_sheet('Result');noise['A1']='Pretend existing answers: must not be read.';noise['B2']=123456
        wb.properties.creator='AssayPilot contributors';wb.save(OUT/filename)
    # A physical 384-well mapping with deliberately different well ordering.
    physical=[f'{r}{c}' for r in 'ABCDEFGHIJKLMNOP' for c in range(1,25)]
    mapped=[{'well':physical[i+240],**d} for i,d in enumerate(data)]
    with (OUT/'design-384.tsv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['well','sample','concentration','unit','role'],delimiter='\t',extrasaction='ignore');writer.writeheader();writer.writerows(mapped)
    wb=Workbook();ws=wb.active;ws.title='Plate384';ws.append(['']+list(range(1,25)))
    values={d['well']:d['value'] for d in mapped}
    for row in 'ABCDEFGHIJKLMNOP':ws.append([row]+[values.get(row+str(c)) for c in range(1,25)])
    wb.properties.creator='AssayPilot contributors';wb.save(OUT/'matrix-384.xlsx')
    print('Flexible synthetic examples generated in data/flexible.')
if __name__=='__main__':main()
