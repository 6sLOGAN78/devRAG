# Docling Serve CPU image inspection — Plan 06-26

Inspected 2026-11-05 local time from `ghcr.io/docling-project/docling-serve-cpu@sha256:7b31b3c2efa17534dfcffb61665b71bbc959ad309b5b7ed82c3bbdcc63cc3d58` (Linux amd64). Docker reports `7,566,848,198` bytes unpacked. The application image label reports `v1.38.2`, source revision `9c058dbb58f61021e3a16e37edb8a7527b2cb2d4`, and MIT; the inherited CentOS label says GPLv2. These labels apply at different layers and are not an overall legal determination.

The preloaded `/opt/app-root/src/.cache/docling/models` directory occupies about 871 MB. Its four Hugging Face repository snapshots and embedded card labels are:

| Model repository | Embedded snapshot revision from `README.md.metadata` | Embedded card label | Principal bundled weights |
| --- | --- | --- | --- |
| `docling-project/docling-layout-heron` | `8f39ad3c0b4c58e9c2d2c84a38465abf757272d8` | Apache-2.0 | `model.safetensors` 171,658,996 B |
| `docling-project/docling-layout-heron-onnx` | `40bde044036bb181c130ddf6c51792187268748f` | Apache-2.0 | `model.onnx` 171,220,471 B |
| `docling-project/docling-models` | `fc0f2d45e2218ea24bce5045f58a389aed16dc23` | CDLA-Permissive-2.0 | TableFormer accurate 212,758,388 B; fast 145,453,276 B |
| `docling-project/DocumentFigureClassifier-v2.5` | `f859dfbff5c9916cd996942d4b0db7fa25808220` | MIT | ONNX 16,940,439 B; safetensors 16,378,200 B |

The image also contains three EasyOCR 1.7.2 weights (`craft_mlt_25k.pth`, `english_g2.pth`, `latin_g2.pth`). The installed EasyOCR package declares Apache License 2.0, and its `config.py` lists upstream release URLs and MD5 values. All three image weights matched those listed MD5 values. No separate model-specific license file was found for these EasyOCR weights; retain that provenance limit.

RapidOCR 3.10.0 declares Apache-2.0 and includes `MODEL_LICENSES.md` distinguishing the source code from upstream PaddleOCR model artifacts. The image's three default ONNX weights matched that notice's SHA-256 values: `PP-OCRv6_det_small.onnx` `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f`, `PP-OCRv6_rec_small.onnx` `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884`, and `ch_ppocr_mobile_v2.0_cls_mobile.onnx` `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c`. The image also carries corresponding `.pth` files and a recognition dictionary; their identities are bound by the image digest but are not individually attributed by that ONNX notice.

The service ran with Docker `--network none`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, 3 GiB memory and 2 CPU quota. It reached application startup complete about 9.43 s after container start. A one-page PDF parsed successfully without network access. Cgroup memory peak was `1,727,893,504` bytes, with zero OOM events. The image consumed enough disk that the 6 GiB free-space reserve requires removing unused build cache or running it sequentially; no project volume was deleted. This inspection and probe do not establish general license clearance or Phase 6 completion.
