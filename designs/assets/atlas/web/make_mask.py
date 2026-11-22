# Builds web/land.webp: keys the flat navy sky out of land.png (flood fill from the top + colour unmixing at the edge).
# usage: python3 make_mask.py ../land.png out_rgba.png  then  cwebp -q 90 -alpha_q 100 -exact out_rgba.png -o land.webp
from PIL import Image, ImageDraw, ImageFilter
import numpy as np, json, sys
src=sys.argv[1]; out=sys.argv[2]
im=Image.open(src).convert('RGB'); a=np.asarray(im).astype(np.float32)
H,W,_=a.shape
S=np.array([21.2,35.0,62.6],np.float32)
# per-row sky estimate from the clean middle top region is constant; use it
d=np.sqrt(((a-S)**2).sum(2))
cand=(d<9).astype(np.uint8)*255
ci=Image.fromarray(cand).copy()
for x in range(0,W,16): 
    if cand[0,x]==255: ImageDraw.floodfill(ci,(x,0),128)
sky=(np.asarray(ci)==128)
# fill tiny holes (specks) in sky: close via min/max filter
skyI=Image.fromarray((sky*255).astype(np.uint8))
skyI=skyI.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
sky=np.asarray(skyI)>127
# boundary band: within 3px of sky
near=np.asarray(skyI.filter(ImageFilter.MaxFilter(7)))>127
# colour-based alpha in the band
T=34.0
ac=np.clip((d-5)/T,0,1)
alpha=np.where(sky,0.0,np.where(near,ac,1.0)).astype(np.float32)
# soften slightly
al=Image.fromarray((alpha*255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7))
alpha=np.minimum(np.asarray(al).astype(np.float32)/255, np.where(sky,0.0,1.0)+0.0)
alpha=np.asarray(al).astype(np.float32)/255
alpha[sky & ~(np.asarray(Image.fromarray((~sky*255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3)))>127)]=0
# unmix foreground colour
A=np.clip(alpha,1e-3,1)[...,None]
F=np.clip((a-(1-A)*S)/A,0,255)
F=np.where(alpha[...,None]>0.02,F,0)
rgba=np.dstack([F,alpha*255]).astype(np.uint8)
Image.fromarray(rgba,'RGBA').save(out)
# skyline: topmost alpha>0.5 per column
col=[int(np.argmax(alpha[:,x]>0.5)) for x in range(W)]
print('skyline min',min(col),'max',max(col))
json.dump(col[::8],open(out+'.skyline.json','w'))
# warm lights
r,g,b=a[...,0],a[...,1],a[...,2]
warm=(r>200)&(g>130)&(b<140)
ys,xs=np.nonzero(warm); print('warm px',len(xs))
# cluster coarse
from collections import defaultdict
cl=defaultdict(list)
for y,x in zip(ys,xs): cl[(y//14,x//14)].append((x,y))
for k,v in sorted(cl.items(),key=lambda kv:-len(kv[1]))[:20]:
    v=np.array(v); print(len(v), v.mean(0).round(0))
