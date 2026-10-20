# Classic TIFF recognition — source review candidate

Status: **UNCONNECTED / NOT_RUNTIME_ACCEPTED**. This archive contains a source fix for `tools/vision_tools_image_prep.py`; it does not connect the patch to the installed product.

The existing local image resolver refuses valid classic TIFF data before the existing PNG normalizer can handle it. The patch recognizes little-endian and big-endian classic TIFF signatures as `image/tiff`. The existing decoder, byte and pixel limits still validate the data. File extensions do not override its bytes. BigTIFF remains unrecognized.

Independent checks executed the actual local `tools.vision_tools._prepare_image(validate_decode=True)` source route with the complete changed preparation module: nine positive and six negative controls passed. Classic TIFF data reached PNG conversion with the synthetic dimensions and pixels preserved; PNG, JPEG, GIF, BMP and WebP controls retained their behavior, malformed data was refused, and no temporary files leaked. This is focused local source evidence. It does not prove installed execution, model interpretation, catalogue coverage, general TIFF fidelity, multipage handling or BigTIFF support.

The initial test environment lacked `ruamel.yaml`. The integrator supplied the exact pure Python wheel already pinned by the source lockfile in a private test directory. Independent checks reverified that wheel and all extracted files, then exercised the real preparation route without a shared-environment install. The earlier blocked result remains in private evidence. No model or Telegram request ran.

`SOURCE.json` records the exact before/after code and public patch hashes plus private evidence hashes. Test fixtures, expected outputs and private logs are excluded. The public patch uses canonical relative paths and zero context to avoid publishing private source paths; applying it requires the exact original source and `git apply --unidiff-zero`. It changes the same three added lines as the reviewed candidate.

Integration and ordinary post-install retesting remain pending. `LICENSE` retains the existing Hermes MIT attribution.
