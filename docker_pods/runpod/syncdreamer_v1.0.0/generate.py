import argparse
from pathlib import Path

import numpy as np
import torch
from ldm.models.diffusion.sync_dreamer import SyncDDIMSampler, SyncMultiviewDiffusion
from ldm.util import instantiate_from_config, prepare_inputs
from omegaconf import OmegaConf
from skimage.io import imsave


def load_model(cfg, ckpt, strict=True):
    config = OmegaConf.load(cfg)
    model = instantiate_from_config(config.model)
    print(f"loading model from {ckpt} ...")
    ckpt = torch.load(ckpt, map_location="cpu")
    model.load_state_dict(ckpt["state_dict"], strict=strict)
    model = model.cuda().eval()
    return model


def generate(
    cfg="configs/syncdreamer.yaml",
    ckpt="ckpt/syncdreamer-step80k.ckpt",
    output=None,
    input=None,
    elevation=None,
    sample_num=4,
    crop_size=-1,
    cfg_scale=2.0,
    batch_view_num=8,
    seed=6033,
    sampler="ddim",
    sample_steps=50,
):
    torch.random.manual_seed(seed)
    np.random.seed(seed)

    model = load_model(cfg, ckpt, strict=True)
    assert isinstance(model, SyncMultiviewDiffusion)
    Path(output).mkdir(exist_ok=True, parents=True)

    # prepare data
    data = prepare_inputs(input, elevation, crop_size)
    for k, v in data.items():
        data[k] = v.unsqueeze(0).cuda()
        data[k] = torch.repeat_interleave(data[k], sample_num, dim=0)

    if sampler == "ddim":
        sampler = SyncDDIMSampler(model, sample_steps)
    else:
        raise NotImplementedError
    x_sample = model.sample(sampler, data, cfg_scale, batch_view_num)

    B, N, _, H, W = x_sample.shape
    x_sample = (torch.clamp(x_sample, max=1.0, min=-1.0) + 1) * 0.5
    x_sample = x_sample.permute(0, 1, 3, 4, 2).cpu().numpy() * 255
    x_sample = x_sample.astype(np.uint8)

    for bi in range(B):
        output_fn = Path(output) / f"{bi}.png"
        imsave(output_fn, np.concatenate([x_sample[bi, ni] for ni in range(N)], 1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cfg", type=str, default="configs/syncdreamer.yaml")
    parser.add_argument("--ckpt", type=str, default="ckpt/syncdreamer-step80k.ckpt")
    parser.add_argument("--output", type=str, required=True)
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--elevation", type=float, required=True)

    parser.add_argument("--sample_num", type=int, default=4)
    parser.add_argument("--crop_size", type=int, default=-1)
    parser.add_argument("--cfg_scale", type=float, default=2.0)
    parser.add_argument("--batch_view_num", type=int, default=8)
    parser.add_argument("--seed", type=int, default=6033)

    parser.add_argument("--sampler", type=str, default="ddim")
    parser.add_argument("--sample_steps", type=int, default=50)
    flags = parser.parse_args()

    generate(
        flags.cfg,
        flags.ckpt,
        flags.output,
        flags.input,
        flags.elevation,
        flags.sample_num,
        flags.crop_size,
        flags.cfg_scale,
        flags.batch_view_num,
        flags.seed,
        flags.sampler,
        flags.sample_steps,
    )


if __name__ == "__main__":
    main()
