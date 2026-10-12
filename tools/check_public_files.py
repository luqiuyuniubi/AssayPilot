"""Check tracked paths and redact findings; complements hosted secret scanning."""
import json,re,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def files():
    result=subprocess.run(['git','ls-files','-z'],cwd=ROOT,capture_output=True)
    if result.returncode:raise RuntimeError('Initialize Git and stage intended public files before running this check.')
    names=[n for n in result.stdout.decode('utf-8').split('\0') if n]
    if not names:raise RuntimeError('No tracked/staged files to check.')
    return [ROOT/n for n in names]
def inspect():
    failures=[];paths=files()
    for path in paths:
        rel=path.relative_to(ROOT)
        forbidden={'.local','.venv','.checks','.browser-check','delivery-check','__pycache__'}
        if any(p in forbidden for p in rel.parts) or path.name.startswith('~$') or path.name=='.env' or path.suffix.lower() in ('.pem','.key','.log','.zip'):failures.append(str(rel)+': private path');continue
        if path.suffix.lower() in ('.xlsx','.docx'):
            with zipfile.ZipFile(path) as z:data=b'\n'.join(z.read(n) for n in z.namelist() if n.endswith('.xml'))
        else:data=path.read_bytes()
        text=data.decode('utf-8',errors='ignore')
        enterprise_words=(''.join(map(chr,[20808,22768])),'Sim'+'cere','C:'+chr(92)+'Users'+chr(92)+'Admin'+'istrator')
        if any(word in text for word in enterprise_words):failures.append(str(rel)+': enterprise or local identity marker')
        # Do not print matches: findings can themselves be credentials.
        if re.search(r'(?i)\b(sk-[a-z0-9_-]{20,}|gh[pousr]_[a-z0-9]{30,}|github_pat_[a-z0-9_]{30,})',text):failures.append(str(rel)+': credential-like value')
    if failures:raise RuntimeError('Public check failed:\n'+'\n'.join(failures))
    manifest=json.loads((ROOT/'data'/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('synthetic') is not True:raise RuntimeError('Synthetic provenance missing.')
    if (ROOT/'pharma_agent'/'company_report.py').exists() or (ROOT/'pharma_agent'/'templates').exists():raise RuntimeError('Enterprise template adapter is not part of the public release.')
    print('Public tracked paths, common secret patterns and synthetic provenance verified. This is not a complete secret detector.')
if __name__=='__main__':inspect()
