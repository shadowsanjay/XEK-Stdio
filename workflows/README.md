# ComfyUI workflow contracts

Default: `flux-schnell-gguf.json` uses FLUX.1-schnell Q4_0, quantized T5, CLIP-L and its VAE.
Install ComfyUI-GGUF and the model files using models/INSTALL.md. Filenames are configurable in
`.env`. This graph uses four diffusion steps, CFG 1 and zero negative conditioning as a distilled
model workflow. Negative prompts and identity references are not falsely advertised as supported.
On the inspected 4 GiB GPU, use low-VRAM offload and sufficient free RAM; live fit is unverified.

`image.json` is a standard-node image graph. Replace its checkpoint filename with your installed
licensed checkpoint. No weights are included. This graph does not condition on references:
supplying references intentionally fails instead of silently ignoring them.

`video.json` supplies a native Wan2.2 TI2V 5B I2V graph, based on the official node structure, with
FLUX keyframes, up to five-second clips, 24 fps and 4n+1 frame counts. This graph is not live-tested
on the inspected 4 GiB GPU. Install its exact weights/nodes on a compatible host and validate first.
`flux-schnell-fp8.json` provides a larger checkpoint alternative for higher-memory machines.

For other Wan/LTX variants, export a working API-format workflow and wrap it:
```json
{
  "capabilities": {"provider":"wan-or-ltx", "width":832, "height":480, "fps":24,
                   "max_duration":5, "reference_conditioning":false},
  "bindings": {"positive":{"node":"YOUR_NODE","input":"text"},
               "seed":{"node":"YOUR_SAMPLER","input":"seed"},
               "frames":{"node":"YOUR_LATENT_NODE","input":"length"}},
  "output_node":"YOUR_SAVE_NODE", "output_key":"gifs", "prompt":{}
}
```
Save as `video.json`. The empty prompt above is documentation only; the application does not
ship/submit it as a working graph. Use actual installed nodes and an MP4-compatible save node.
Set the correct output key (`images`, `gifs`, or `videos`). Only declare supported capabilities.

Binding keys: `positive`, `negative`, `seed`, `duration`, `frames`, `width`, `height`, `reference_0`,
`reference_1`, etc. References are ComfyUI-uploaded paths; map them to LoadImage inputs feeding
an identity-conditioning graph. Every supplied reference must be mapped. Stable seeds and prompts
alone do not ensure identity consistency.

Official routes: https://docs.comfy.org/development/comfyui-server/comms_routes
