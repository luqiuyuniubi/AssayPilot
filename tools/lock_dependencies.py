"""Lock the installed runtime/development graph, excluding the audit helper runtime."""
import importlib.metadata as metadata
from pathlib import Path
from packaging.requirements import Requirement
ROOT=Path(__file__).resolve().parents[1]
def graph(roots):
    found={};todo=list(roots)
    while todo:
        dist=metadata.distribution(todo.pop());name=dist.metadata['Name'].lower().replace('_','-')
        if name in found:continue
        found[name]=dist.version
        for raw in dist.requires or []:
            req=Requirement(raw)
            if req.marker is None or req.marker.evaluate({'extra':''}):todo.append(req.name)
    return found
if __name__=='__main__':
    core=graph(['numpy','scipy','openpyxl','python-docx','matplotlib','defusedxml','fonttools','lxml','pillow'])
    dev=graph(['requests','websocket-client','urllib3','idna'])
    for filename,packages,prefix in [('requirements-lock.txt',core,[]),('requirements-dev-lock.txt',{k:v for k,v in dev.items() if k not in core},['-r requirements-lock.txt']),('requirements-pdf-lock.txt',graph(['PyMuPDF']),[])]:
        lines=['# Validated on Windows x64 / Python 3.11; refresh with tools/lock_dependencies.py',*prefix,*[name+'=='+version for name,version in sorted(packages.items())]]
        (ROOT/filename).write_text('\n'.join(lines)+'\n',encoding='utf-8')
    all_packages={**core,**dev,**graph(['PyMuPDF'])}
    (ROOT/'requirements-audit-lock.txt').write_text('# Flattened runtime, development and optional PDF graph for complete --no-deps auditing.\n'+'\n'.join(name+'=='+version for name,version in sorted(all_packages.items()))+'\n',encoding='utf-8')
    (ROOT/'.checks').mkdir(exist_ok=True)
    (ROOT/'.checks'/'all-dependencies.txt').write_text('\n'.join(name+'=='+version for name,version in sorted(all_packages.items()))+'\n',encoding='utf-8')
    print('Runtime, development and optional PDF dependency locks generated.')
