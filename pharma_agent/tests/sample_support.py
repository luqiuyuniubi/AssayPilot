import csv,io
def rewrite_wells(raw,changes):
    rows=list(csv.reader(io.StringIO(raw.decode('utf-8'))))
    for row in rows:
        if row and row[0] in list('ABCDEFGH'):
            for well,value in changes.items():
                if well[0]==row[0]:row[int(well[1:])]=str(value)
    out=io.StringIO();csv.writer(out).writerows(rows);return out.getvalue().encode('utf-8')
