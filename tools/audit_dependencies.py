"""Query public OSV advisories using dependency names/versions, never source code."""
import argparse,importlib.metadata,json,sys,time,urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from packaging.version import Version,InvalidVersion


def audit():
    packages=[];seen=set()
    for dist in importlib.metadata.distributions():
        name=dist.metadata.get('Name')
        if not name:continue
        key=name.casefold().replace('_','-')
        if key in seen:continue
        seen.add(key)
        try:version=Version(dist.version).public
        except InvalidVersion:version=dist.version
        packages.append({'package':{'name':name,'ecosystem':'PyPI'},'version':version})
    packages.sort(key=lambda row:row['package']['name'].casefold())
    report={'scanner':'https://api.osv.dev/v1/querybatch','packages':packages,'source_upload':False,'complete':False}
    try:
        request=urllib.request.Request(report['scanner'],data=json.dumps({'queries':packages}).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=30) as response:results=json.load(response)['results']
        if len(results)!=len(packages):raise ValueError('Incomplete advisory response')
        report['results']=results;report['complete']=True
        report['findings']=[{**package,'vulns':row['vulns']} for package,row in zip(packages,results) if row.get('vulns')]
    except Exception as error:report['error']=str(error)
    return report


def advisory_details(report):
    identifiers=sorted({vuln['id'] for row in report.get('findings',[]) for vuln in row['vulns']})
    def read(identifier):
        from urllib.parse import quote
        for attempt in range(3):
            try:
                with urllib.request.urlopen('https://api.osv.dev/v1/vulns/'+quote(identifier,safe=''),timeout=15) as response:return identifier,json.load(response)
            except Exception as error:
                if attempt==2:return identifier,{'_error':str(error)}
                time.sleep(.25)
    with ThreadPoolExecutor(max_workers=2) as pool:report['advisories']=dict(pool.map(read,identifiers))
    report['details_complete']=all('_error' not in row for row in report['advisories'].values())
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--details-only',action='store_true');parser.add_argument('--source-runtime',action='store_true');args=parser.parse_args()
    if args.source_runtime:
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from geoforma.runtime_profile import activate_security_profile
        if not activate_security_profile():raise RuntimeError('Source security profile is unavailable')
    report=advisory_details(json.loads(args.output.read_text(encoding='utf-8'))) if args.details_only else audit()
    report['runtime']='source-security-profile' if args.source_runtime else 'interpreter-default'
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    if args.details_only:
        print(json.dumps({identifier:{'summary':row.get('summary'),'affected':[{'name':entry.get('package',{}).get('name'),'ranges':entry.get('ranges'),'versions_count':len(entry.get('versions',[]))} for entry in row.get('affected',[])]} for identifier,row in report['advisories'].items()}))
    else:print(json.dumps({key:report[key] for key in ('complete','error','findings') if key in report}))
    sys.exit(0 if report['complete'] and not report['findings'] else 1)
