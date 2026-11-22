"""Paint art for the Token Burn designs with Qwen-Image-Edit-2511 (local, both 3090s).

    ~/venvs/qwenedit/bin/python tools/gen_art.py jobs.json [--only name1 name2] [--redo]

jobs.json: [{"name": "bakery/bg", "prompt": "...", "w": 1664, "h": 928,
             "ref": "optional/path.png" or ["a.png","b.png"], "seed": 1,
             "cutout": true, "steps": 40, "negative": "..."}]
Writes designs/assets/<name>.png (and <name>.cut.png with transparent background when cutout).
With no ref, the model edits a blank canvas, i.e. plain text-to-image.
Transformer in fp8 on cuda:0 (~20 GB), the 7B text encoder on cuda:1 (as in millennium rigs/gen/make_refs.py).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import torch
from PIL import Image

HERE = Path(__file__).resolve().parent.parent
ASSETS = HERE / "designs" / "assets"
REPO = "Qwen/Qwen-Image-Edit-2511"
NEG = ("low quality, blurry, jpeg artifacts, watermark, signature, text, letters, logo, deformed hands, "
       "extra fingers, extra limbs, bad anatomy, cropped, frame, border, ugly, noisy")


def load():
    from diffusers import QwenImageEditPlusPipeline, QwenImageTransformer2DModel
    t0 = time.time()
    tr = QwenImageTransformer2DModel.from_pretrained(REPO, subfolder="transformer", torch_dtype=torch.bfloat16)
    tr.enable_layerwise_casting(storage_dtype=torch.float8_e4m3fn, compute_dtype=torch.bfloat16)
    tr.to("cuda:0")
    pipe = QwenImageEditPlusPipeline.from_pretrained(REPO, transformer=tr, torch_dtype=torch.bfloat16)
    pipe.vae.to("cuda:0")
    pipe.vae.enable_tiling()
    pipe.text_encoder.to("cuda:1")
    type(pipe)._execution_device = property(lambda self: torch.device("cuda:0"))
    print(f"loaded in {time.time() - t0:.0f}s", flush=True)
    return pipe


def encode(pipe, text, imgs):
    from diffusers.pipelines.qwenimage.pipeline_qwenimage_edit_plus import CONDITION_IMAGE_SIZE, calculate_dimensions
    conds = []
    for img in imgs:
        w, h = calculate_dimensions(CONDITION_IMAGE_SIZE, img.width / img.height)
        conds.append(pipe.image_processor.resize(img, h, w))
    with torch.no_grad():
        emb, mask = pipe.encode_prompt(text, image=conds, device=torch.device("cuda:1"))
    return emb.to("cuda:0"), None if mask is None else mask.to("cuda:0")


_seg = None


def cutout(img: Image.Image) -> Image.Image:
    global _seg
    from torchvision import transforms
    from transformers import AutoModelForImageSegmentation
    if _seg is None:
        _seg = AutoModelForImageSegmentation.from_pretrained("ZhengPeng7/BiRefNet", trust_remote_code=True)
        _seg.to("cuda:1").float().eval()
    tf = transforms.Compose([transforms.Resize((1024, 1024)), transforms.ToTensor(),
                             transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
    x = tf(img.convert("RGB")).unsqueeze(0).to("cuda:1")
    with torch.no_grad():
        pred = _seg(x)[-1].sigmoid().cpu()[0].squeeze()
    mask = transforms.ToPILImage()(pred).resize(img.size, Image.LANCZOS)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out.crop(out.getbbox() or (0, 0, *out.size))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("jobs")
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--redo", action="store_true")
    a = ap.parse_args()
    jobs = json.loads(Path(a.jobs).read_text())
    if a.only:
        jobs = [j for j in jobs if j["name"] in a.only or any(j["name"].startswith(o.rstrip("*")) for o in a.only if o.endswith("*"))]
    todo = [j for j in jobs if a.redo or a.only or not (ASSETS / f"{j['name']}.png").exists()]
    print(f"{len(jobs)} jobs, {len(todo)} to paint", flush=True)
    if not todo:
        return 0
    pipe = load()
    for n, j in enumerate(todo, 1):
        t0 = time.time()
        w, h = j.get("w", 1024), j.get("h", 1024)
        w, h = w // 16 * 16, h // 16 * 16
        refs = j.get("ref") or []
        refs = [refs] if isinstance(refs, str) else refs
        imgs = [Image.open(ASSETS / r if not Path(r).is_absolute() else r).convert("RGB") for r in refs]
        prompt = j["prompt"]
        if not imgs:
            imgs = [Image.new("RGB", (w, h), (255, 255, 255))]
            prompt = "Replace this blank white canvas entirely with a new image: " + prompt
        pe, pm = encode(pipe, prompt, imgs)
        ne, nm = encode(pipe, j.get("negative", NEG), imgs)
        out = pipe(image=imgs, prompt_embeds=pe, prompt_embeds_mask=pm,
                   negative_prompt_embeds=ne, negative_prompt_embeds_mask=nm,
                   true_cfg_scale=j.get("cfg", 4.0), guidance_scale=1.0,
                   num_inference_steps=j.get("steps", 40), width=w, height=h,
                   generator=torch.Generator("cuda:0").manual_seed(j.get("seed", 0))).images[0]
        p = ASSETS / f"{j['name']}.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        out.save(p)
        if j.get("cutout"):
            cutout(out).save(ASSETS / f"{j['name']}.cut.png")
        print(f"[{n}/{len(todo)}] {j['name']} {w}x{h} {time.time() - t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
