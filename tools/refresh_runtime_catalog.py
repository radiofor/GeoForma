"""Maintainer-only: pin Windows wheels from the official PyTorch simple index."""
import hashlib,html,json,re,sys
from pathlib import Path
from urllib.parse import unquote,urlsplit,urlunsplit
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]

def main():
    profiles={}
    for profile,title in [('cpu','CPU'),('cu126','NVIDIA GPU')]:
        wheels=[]
        for name,version in [('torch','2.13.0'),('torchvision','0.28.0')]:
            index=f'https://download.pytorch.org/whl/{profile}/{name}/'
            text=urlopen(index,timeout=30).read().decode()
            filename=f'{name}-{version}+{profile}-cp313-cp313-win_amd64.whl'
            links=[html.unescape(x) for x in re.findall('href="([^"]+)"',text) if unquote(x.split('#')[0]).endswith('/'+filename)]
            if len(links)!=1:raise ValueError('Expected exactly one official wheel: '+filename)
            parts=urlsplit(links[0]);digest=parts.fragment.removeprefix('sha256=')
            url=urlunsplit(parts._replace(fragment=''))
            with urlopen(Request(url,method='HEAD'),timeout=30) as response:size=int(response.headers['Content-Length'])
            provenance='official-index'
            if not re.fullmatch('[a-f0-9]{64}',digest):
                hasher=hashlib.sha256()
                with urlopen(url,timeout=60) as response:
                    while block:=response.read(4*1024**2):hasher.update(block)
                digest=hasher.hexdigest();provenance='maintainer-digest-of-official-https-file'
            wheels.append(dict(name=name,version=version+'+'+profile,filename=filename,url=url,sha256=digest,bytes=size,hash_source=provenance))
        profiles[profile]=dict(title=title,wheels=wheels)
    value=dict(kind='geoforma-native-runtime-v1',python='cp313',platform='win_amd64',profiles=profiles)
    target=ROOT/'geoforma/native_runtime_catalog.json'
    target.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    print(target)
    for key,profile in profiles.items():print(key,sum(w['bytes'] for w in profile['wheels']))

if __name__=='__main__':main()
