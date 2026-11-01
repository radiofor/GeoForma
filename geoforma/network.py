"""HTTPS downloads use the maintained CA bundle and reject protocol downgrades."""
import ssl
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler,HTTPSHandler,build_opener
from urllib.error import HTTPError
import certifi


class HTTPSRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,message,headers,newurl):
        if urlsplit(newurl).scheme.lower()!='https':raise HTTPError(newurl,code,'HTTPS downgrade rejected',headers,fp)
        return super().redirect_request(request,fp,code,message,headers,newurl)


def open_https(request,timeout=15):
    url=request.full_url if hasattr(request,'full_url') else str(request)
    if urlsplit(url).scheme.lower()!='https':raise ValueError('下载地址必须使用 HTTPS。')
    context=ssl.create_default_context(cafile=certifi.where());context.minimum_version=ssl.TLSVersion.TLSv1_2
    return build_opener(HTTPSHandler(context=context),HTTPSRedirectHandler()).open(request,timeout=timeout)
