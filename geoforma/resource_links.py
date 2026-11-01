"""Official resource links shared by the download view and copied instructions."""
import html
from urllib.parse import urlsplit

PYTORCH_HOME='https://pytorch.org/get-started/locally/'
SAM_HOME='https://github.com/facebookresearch/segment-anything'
SAM2_HOME='https://github.com/facebookresearch/sam2'


def model_home(spec):
    if spec['backend']=='sam3':return 'https://huggingface.co/1038lab/sam3/tree/main'
    return SAM_HOME if spec['backend']=='sam' else SAM2_HOME


def size_text(value):return f'{value/1024**2:,.1f} MiB' if value<1024**3 else f'{value/1024**3:,.2f} GiB'


def download_html(files,homepage):
    escape=html.escape
    source=urlsplit(homepage)
    caption=source.netloc+(source.path if source.netloc=='github.com' else '')
    sections=['<p style="margin:0 0 10px 0;color:#5e7684">来源　<a href="'+escape(homepage,quote=True)+'">'+escape(caption)+'</a></p>']
    for item in files:
        rows=[('文件',item['filename']),('大小',size_text(item['bytes'])),('SHA256',item['sha256'].upper())]
        sections.append('<table width="100%" cellspacing="0" cellpadding="5">'+''.join(
            '<tr><td width="64" valign="top" style="color:#5e7684">'+label+'</td><td>'+escape(value)+'</td></tr>' for label,value in rows)+'</table>')
    return ''.join(sections)


def download_text(files,homepage):
    return '下载来源\n'+homepage+'\n\n'+'\n\n'.join(
        item['filename']+'\n'+item['url']+'\nSHA256 '+item['sha256'].upper() for item in files)
