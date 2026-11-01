"""Stable category colors; no Qt state, geometry changes or extra dependencies."""
import colorsys
from functools import lru_cache
import re

PALETTE=('#EF3340','#3465DF','#16934D','#9949CE','#ED761B','#D83191','#008B94','#85931C')
HIGHLIGHTS=('#ffce45','#21d4ed')


def normalize_color(value):
    if not isinstance(value,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value):
        raise ValueError('类别颜色必须为 #RRGGBB 格式。')
    return value.upper()


@lru_cache(maxsize=65534)
def default_color(identifier):
    index=max(0,int(identifier)-1)
    if index<len(PALETTE):return PALETTE[index]
    # Do not cycle through the short palette for older projects with many IDs.
    hue=(index*.618033988749895+.07)%1
    rgb=colorsys.hsv_to_rgb(hue,.72+.08*(index%3),.82+.07*(index%2))
    return '#'+''.join(f'{round(value*255):02X}' for value in rgb)


def class_color(category):
    return normalize_color(category['color']) if 'color' in category else default_color(category['id'])


def color_map(categories):return {category['id']:class_color(category) for category in categories}


def _rgb(color):return tuple(int(color[i:i+2],16) for i in (1,3,5))


def _distance(first,second):
    # A weighted RGB separation heuristic, with extra weight on green/blue.
    return sum(weight*(a-b)**2 for weight,a,b in zip((2,4,3),first,second))


def allocate_color(identifier,categories):
    """Prefer the stable palette; otherwise maximize separation from used colors."""
    used={class_color(category) for category in categories}
    highlights={color.upper() for color in HIGHLIGHTS}
    reserved=[_rgb(color) for color in used|highlights]
    preferred=default_color(identifier)
    if preferred not in used and min(_distance(_rgb(preferred),color) for color in reserved)>=12000:return preferred
    candidates=list(PALETTE)+[default_color(identifier+step) for step in range(8,104)]
    candidates=[color for color in dict.fromkeys([preferred]+candidates) if color not in used and color not in highlights]
    if not candidates:
        # An odd stride visits distinct RGB values, so even an exhausted hue
        # candidate pool cannot cause an unbounded search for a large catalog.
        for step in range(len(used)+len(HIGHLIGHTS)+1):
            color=f'#{(identifier*0x9e3779+step*0x5bd1e9)&0xffffff:06X}'
            if color not in used and color not in highlights:return color
        raise ValueError('可用类别颜色已用完。')
    return max(candidates,key=lambda color:min(_distance(_rgb(color),other) for other in reserved))
