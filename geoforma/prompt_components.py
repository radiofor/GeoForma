"""Keep the foreground component selected by a real positive pixel."""
import numpy as np
from PIL import Image,ImageDraw


def anchored_mask(mask,window,anchor):
    x,y=int(np.floor(anchor[0]-window[0])),int(np.floor(anchor[1]-window[1]))
    if not (0<=y<mask.shape[0] and 0<=x<mask.shape[1]) or not mask[y,x]:return None
    # Four-connected fill visits the selected object only, preserving holes and
    # excluding unrelated islands without a minimum-area/colour heuristic.
    image=Image.fromarray(np.asarray(mask,dtype=np.uint8)).copy()
    ImageDraw.floodfill(image,(x,y),2)
    return np.asarray(image)==2
