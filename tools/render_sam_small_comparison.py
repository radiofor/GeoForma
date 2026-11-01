"""Compact visible examples; no assertions about human ground-truth accuracy."""
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'experiments/sam_versions'
models=['sam1_vit_b','sam2.1_tiny','sam2.1_small','sam2.1_large'];keys=['high_L28_detail','high_L29_detail','low_L28_detail','low_L29_detail']
sheet=Image.new('RGB',(1400,1200),(20,28,36));d=ImageDraw.Draw(sheet)
for row,key in enumerate(keys):
    sheet.paste(Image.open(OUT/'fixtures'/(key+'_rgb.png')),(0,row*300+20));d.text((6,row*300+4),key+' RGB',fill='white')
    for column,model in enumerate(models,1):
        sheet.paste(Image.open(OUT/'windows'/model/'cuda'/(key+'_refine.png')),(column*280,row*300+20));d.text((column*280+6,row*300+4),model,fill='white')
sheet.save(OUT/'small_lakes_comparison.png');print('small lake comparison ready',flush=True)
