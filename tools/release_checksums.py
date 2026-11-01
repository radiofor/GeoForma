import argparse,hashlib,json,re
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from geoforma.distribution import VERSION

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--folder',type=Path,default=ROOT/'release'/VERSION/'installer');args=parser.parse_args()
    folder=args.folder.resolve();rows=[]
    for path in sorted(folder.glob('GeoForma-'+VERSION+'-win64-setup*')):
        if path.suffix not in ['.exe','.bin']:continue
        with path.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
        rows.append({'file':path.name,'bytes':path.stat().st_size,'sha256':checksum})
    prefix='GeoForma-'+VERSION+'-win64-setup'
    volumes=sorted(int(match[1]) for row in rows if (match:=re.fullmatch(re.escape(prefix)+r'-(\d+)\.bin',row['file'])))
    if (not any(row['file']==prefix+'.exe' for row in rows) or (volumes and volumes!=list(range(1,max(volumes)+1)))
        or len(rows)!=len(volumes)+1 or any(row['bytes']==0 for row in rows)):raise ValueError('Installer volume set is incomplete')
    (folder/'SHA256SUMS.txt').write_text('\n'.join(row['sha256']+'  '+row['file'] for row in rows)+'\n',encoding='utf-8')
    (folder/'files.json').write_text(json.dumps({'version':VERSION,'files':rows},indent=2),encoding='utf-8')
    print('Verified',len(rows),'installer files',sum(row['bytes'] for row in rows),flush=True)

if __name__=='__main__':main()
