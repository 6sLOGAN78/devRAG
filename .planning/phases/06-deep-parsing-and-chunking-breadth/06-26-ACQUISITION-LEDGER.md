# Plan 06-26 acquisition ledger

## 2026-11-04 — Docling CPU image

The operator approved the exact [supplemental packet](06-26-SUPPLEMENTAL-ACQUISITION.md); the [decision record](06-26-SUPPLEMENTAL-APPROVAL.json) binds its SHA-256. No other package, image or model was acquired in this attempt.

- Before pull: filesystem free `13,350,666,240` bytes. Host `vm.max_map_count=262144`; the existing devRAG stack was healthy.
- Pulled only `ghcr.io/docling-project/docling-serve-cpu@sha256:7b31b3c2efa17534dfcffb61665b71bbc959ad309b5b7ed82c3bbdcc63cc3d58` for Linux amd64. Docker reported the same manifest digest. `docker image inspect` reported image ID matching that manifest and unpacked size `7,566,848,198` bytes. The image label reports version `v1.38.2` and source revision `9c058dbb58f61021e3a16e37edb8a7527b2cb2d4`.
- After the pull settled: filesystem free `5,770,133,504` bytes, below the packet's required 6 GiB reserve (`6,442,450,944` bytes). This is a **failed disk guard**. Acquisition and all new service execution stopped before any container was started or any PDF was submitted.
- The newly pulled image remains present pending the narrow cleanup decision required by the Docker destructive-command guardrail. It is the only target proposed for removal; existing devRAG images, containers, volumes and build cache remain untouched. No Docling bundled-model inventory, real parse, MinerU acquisition, or MinerU real parse is claimed.

Next: remove the newly pulled Docling image if authorized, verify the disk reserve, then reassess how to run each fixed probe without exceeding the approved footprint. A different image, package or model needs a revised checkpoint.
