"""Deterministic Store identity, manifest and file mapping contracts."""
import hashlib,re
from pathlib import Path,PureWindowsPath
import xml.etree.ElementTree as ET

FOUNDATION='http://schemas.microsoft.com/appx/manifest/foundation/windows10'
UAP='http://schemas.microsoft.com/appx/manifest/uap/windows10'
UAP10='http://schemas.microsoft.com/appx/manifest/uap/windows10/10'
RESCAP='http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities'


def publisher_id(publisher):
    alphabet='0123456789abcdefghjkmnpqrstvwxyz'
    value=int.from_bytes(hashlib.sha256(publisher.encode('utf-16le')).digest()[:8],'big')<<1
    return ''.join(alphabet[(value>>shift)&31] for shift in range(60,-1,-5))


def validate_identity(profile):
    name=profile.get('identity_name');publisher=profile.get('publisher');display=profile.get('publisher_display_name');app=profile.get('app_id')
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{2,49}',name):raise ValueError('商店包名称无效。')
    if not isinstance(publisher,str) or not publisher.startswith('CN=') or any(char in publisher for char in '\r\n\0'):raise ValueError('商店发布者无效。')
    if not isinstance(display,str) or not display.strip():raise ValueError('发布者显示名称为空。')
    if not isinstance(app,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9.]{0,63}',app):raise ValueError('应用 ID 无效。')
    family=name+'_'+publisher_id(publisher)
    if profile.get('package_family_name')!=family:raise ValueError('发布者与截图中的包族名不匹配。')
    return family


def package_version(version):
    parts=version.split('.')
    if len(parts) not in (3,4) or any(not part.isdigit() or not 0<=int(part)<=65535 for part in parts) or int(parts[0])==0 or len(parts)==4 and int(parts[3])!=0:raise ValueError('商店版本须为三个数字或末位为 0 的四段数字。')
    if len(parts)==3:parts.append('0')
    return '.'.join(str(int(part)) for part in parts)


def manifest_bytes(profile,version):
    validate_identity(profile)
    for prefix,namespace in (('',FOUNDATION),('uap',UAP),('uap10',UAP10),('rescap',RESCAP)):ET.register_namespace(prefix,namespace)
    tag=lambda name:'{'+FOUNDATION+'}'+name
    package=ET.Element(tag('Package'),{'IgnorableNamespaces':'uap uap10 rescap'})
    ET.SubElement(package,tag('Identity'),{'Name':profile['identity_name'],'Publisher':profile['publisher'],'Version':package_version(version),'ProcessorArchitecture':'x64'})
    properties=ET.SubElement(package,tag('Properties'))
    for name,text in (('DisplayName','GeoForma'),('PublisherDisplayName',profile['publisher_display_name']),('Description','GeoForma 遥感影像交互标注工具'),('Logo',r'StoreAssets\StoreLogo.png')):
        ET.SubElement(properties,tag(name)).text=text
    resources=ET.SubElement(package,tag('Resources'));ET.SubElement(resources,tag('Resource'),{'Language':'zh-CN'})
    dependencies=ET.SubElement(package,tag('Dependencies'))
    ET.SubElement(dependencies,tag('TargetDeviceFamily'),{'Name':'Windows.Desktop','MinVersion':'10.0.22000.0','MaxVersionTested':'10.0.26200.0'})
    applications=ET.SubElement(package,tag('Applications'))
    app=ET.SubElement(applications,tag('Application'),{'Id':profile['app_id'],'Executable':r'App\GeoForma.exe',
        '{'+UAP10+'}RuntimeBehavior':'win32App','{'+UAP10+'}TrustLevel':'mediumIL','{'+UAP10+'}SupportsMultipleInstances':'true'})
    ET.SubElement(app,'{'+UAP+'}VisualElements',{'DisplayName':'GeoForma','Description':'GeoForma 遥感影像交互标注工具',
        'Square150x150Logo':r'StoreAssets\Square150x150Logo.png','Square44x44Logo':r'StoreAssets\Square44x44Logo.png','BackgroundColor':'transparent'})
    capabilities=ET.SubElement(package,tag('Capabilities'));ET.SubElement(capabilities,'{'+RESCAP+'}Capability',{'Name':'runFullTrust'})
    ET.indent(package,space='  ')
    return ET.tostring(package,encoding='utf-8',xml_declaration=True)


def file_mapping(entries):
    lines=['[Files]'];seen=set()
    for source,destination in entries:
        source=Path(source).resolve();destination=PureWindowsPath(destination)
        if (not source.is_file() or '"' in str(source) or not str(destination).isascii() or destination.is_absolute()
            or destination.drive or destination.root or '..' in destination.parts or any(char in str(destination) for char in ('"',':','\0'))):raise ValueError('MSIX 文件映射无效。')
        key=str(destination).casefold()
        if key in seen:raise ValueError('MSIX 目标路径重复。')
        seen.add(key);lines.append('"'+str(source)+'" "'+str(destination)+'"')
    return '\n'.join(lines)+'\n'
