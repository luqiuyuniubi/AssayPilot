"""Package intended tracked files only; personal runtimes never enter the archive."""
import json,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'pharma_agent'))
from server import VERSION
def main():
    result=subprocess.run([sys.executable,str(ROOT/'tools'/'check_public_files.py')],cwd=ROOT)
    if result.returncode:raise RuntimeError('Public file check failed.')
    names=[n for n in subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode('utf-8').split('\0') if n]
    dest=ROOT/'dist';dest.mkdir(exist_ok=True)
    package=dest/('AssayPilot-'+VERSION+'.zip')
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
        for name in names:z.write(ROOT/name,'AssayPilot/'+name)
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        assert not any('/.local/' in n or '/.venv/' in n or '/.checks/' in n for n in z.namelist())
    print(json.dumps({'files':len(names),'version':VERSION,'archive_bytes':package.stat().st_size,'runtime_excluded':True}))
if __name__=='__main__':main()
