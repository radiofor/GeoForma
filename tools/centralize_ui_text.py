"""One-time migration of static labels and message templates into the UI catalog."""
import ast,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
files=list((ROOT/'geoforma/controllers').glob('*.py'))+list((ROOT/'geoforma/ui/panels').glob('*.py'))+[ROOT/'geoforma'/name for name in ('viewport.py','dialogs.py','runtime_dialog.py','model_status.py')]+[ROOT/'geoforma/ui/label_table.py']
catalog={};reverse={};known={'导入影像':'action.import_image','全图候选':'mode.candidates','逐个标注':'mode.individual','应用':'action.apply','自动应用':'option.auto_apply','保存标签':'action.confirm','保存并继续':'action.confirm_next','取消编辑':'action.cancel_edit','删除':'action.delete','调整中':'status.editing','待审':'status.review','已保存':'status.confirmed','环境与帮助':'group.environment_help'}
def has_chinese(s):return bool(re.search('[\u4e00-\u9fff]',s))
for path in files:
    source=path.read_text(encoding='utf-8');module=ast.parse(source);parents={child:node for node in ast.walk(module) for child in ast.iter_child_nodes(node)}
    encoded=source.encode('utf-8');line_offsets=[0]
    for line in source.splitlines(keepends=True):line_offsets.append(line_offsets[-1]+len(line.encode('utf-8')))
    changes=[];serial=0
    def ancestors(node):
        while node in parents:node=parents[node];yield node
    def key_for(value,node):
        global serial
        if value in reverse:return reverse[value]
        serial+=1;function=next((p.name for p in ancestors(node) if isinstance(p,(ast.FunctionDef,ast.AsyncFunctionDef))), 'shared')
        key=known.get(value,f'{path.stem}.{function}.{serial:03}')
        catalog[key]=value;reverse[value]=key;return key
    for node in ast.walk(module):
        if isinstance(node,ast.Constant) and isinstance(node.value,str) and has_chinese(node.value):
            if any(isinstance(p,ast.JoinedStr) for p in ancestors(node)):continue
            key=key_for(node.value,node);replacement=f'ui_text({key!r})'
        elif isinstance(node,ast.JoinedStr) and has_chinese(ast.get_source_segment(source,node) or ''):
            if any(isinstance(p,ast.JoinedStr) for p in ancestors(node)):continue
            template='';params=[];supported=True
            for part in node.values:
                if isinstance(part,ast.Constant):template+=part.value.replace('{','{{').replace('}','}}')
                elif isinstance(part,ast.FormattedValue):
                    name=f'p{len(params)}';spec=''
                    if part.format_spec:
                        if any(not isinstance(v,ast.Constant) for v in part.format_spec.values):supported=False;break
                        spec=':'+''.join(v.value for v in part.format_spec.values)
                    conversion='!'+chr(part.conversion) if part.conversion!=-1 else ''
                    template+='{'+name+conversion+spec+'}';params.append(name+'='+ast.unparse(part.value))
            if not supported:continue
            key=key_for(template,node);replacement=f'ui_text({key!r}).format('+','.join(params)+')'
        else:continue
        start=line_offsets[node.lineno-1]+node.col_offset;stop=line_offsets[node.end_lineno-1]+node.end_col_offset
        changes.append((start,stop,replacement.encode('utf-8')))
    if changes:
        for start,stop,value in sorted(changes,reverse=True):encoded=encoded[:start]+value+encoded[stop:]
        rewritten=encoded.decode('utf-8');tree=ast.parse(rewritten)
        doc=tree.body[0]
        anchor=next((n.end_lineno for n in tree.body if isinstance(n,ast.ImportFrom) and n.module=='__future__'),doc.end_lineno if isinstance(doc,ast.Expr) and isinstance(doc.value,ast.Constant) and isinstance(doc.value.value,str) else 0)
        lines=rewritten.splitlines(keepends=True);depth=len(path.relative_to(ROOT/'geoforma').parts)-1
        prefix='.'*(depth+1)+'ui.text'
        if path.parent==ROOT/'geoforma/ui':prefix='.text'
        lines.insert(anchor,f'from {prefix} import ui_text\n');path.write_text(''.join(lines),encoding='utf-8')
path=ROOT/'geoforma/ui/text.py'
path.write_text('"""Shared desktop labels and message templates; keys are stable English identifiers."""\n\nTEXT = '+json.dumps(catalog,ensure_ascii=False,indent=4)+'\n\n\ndef ui_text(key):\n    return TEXT[key]\n',encoding='utf-8')
print('Centralized',len(catalog),'labels and message templates')
