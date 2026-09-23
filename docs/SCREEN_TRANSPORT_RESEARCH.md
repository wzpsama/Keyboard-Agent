# Screen transport research

## Scope

This note records a read-only review of the legacy protocol experiments. The
production path remains the official `GIF -> Image2Bin -> SerialPortTool`
chain. No direct serial sender is enabled by this work.

## Findings

- The screen accepts a vendor packet format with 2048-byte data blocks and
  region commit packets. The legacy experiments also record acknowledgement
  handling and several observed checksum initial values.
- A raw 320x480 RGB565 image still requires about 307 KiB. Reliable,
  acknowledgement-paced raw writes were observed to be far too slow for pet
  reactions, while blind streaming could leave the panel unresponsive.
- The official GIF output is much smaller because it uses the screen's
  compressed animation format. It is therefore the only proven fast path for
  regular scene changes.
- There is no verified command for selecting an already-stored GIF asset, and
  no verified partial-update command for an `Image2Bin` compressed payload.
  The legacy checksum observations are incomplete for arbitrary compressed
  payload lengths, so they are not a safe basis for a production sender.

## Decision

The product should reduce transport demand above the protocol: scene
transitions, panel-side GIF loops, and pre-converted assets. Direct writes are
not a candidate for routine use until the following evidence exists.

## Next evidence required

1. Capture official-tool traffic for two identical GIF uploads and one changed
   GIF upload, including device acknowledgements.
2. Verify the packet checksum rule across all observed final-payload lengths.
3. Test only one small, reversible GIF upload while the owner is present, then
   confirm that normal keyboard input and a subsequent official upload still
   work.
4. Prove either an asset-selection command or a compressed-payload partial
   update before considering an alternative production sender.

Until then, any direct protocol code remains diagnostic material only.
