# Lottie animation licenses

All four files below were downloaded from LottieFiles.com (the raw Lottie
JSON, not a GIF/MP4 preview) and are covered by LottieFiles' **"Lottie
Simple License"** (full text reproduced at the bottom of this file, sourced
from `https://lottiefiles.com/page/license` on 2026-07-28). Summary: free to
download, use, and modify — including commercial use — with **no attribution
required** (attribution is "strongly encouraged" but optional). Any
redistribution of the *files themselves* (not an app that merely uses them)
must carry the same license terms.

| File | Source URL | Creator (as credited on LottieFiles) | License | Size | Description |
|---|---|---|---|---|---|
| `mascot-idle.json` | https://lottiefiles.com/free-animation/glow-loading-7U7aX5YEUH | LottieFiles (page credited to "LottieFiles", no individual creator name shown) | Lottie Simple License (free, no attribution required) | ~9.9 KB | A small pulsing/glowing orb ("Glow ball" per the animation's internal layer name) — used as the ambient ready-made mascot idle loop replacing the CSS firefly; reads as a soft floating light, fits small at 40-80px. |
| `delight-accent.json` | https://lottiefiles.com/free-animation/looply-03-checkmark-minimal-uMfGgQPq1F | Looply | Lottie Simple License (free, no attribution required) | ~1.7 KB | A minimal checkmark-draw animation ("looply_03_checkmark_minimal") — used as the success/delight accent for moments like accepting an AI edit or finishing an export. Tiny footprint by design. |
| `loading-loop.json` | https://lottiefiles.com/free-animation/loading-spinner-1qXfe3OcDM | Not listed (LottieFiles page shows no individual creator name — og:title field was blank) | Lottie Simple License (free, no attribution required) | ~9.5 KB | A clean, minimal indefinite loading spinner loop. |
| `empty-state.json` | https://lottiefiles.com/free-animation/open-book-0pNUcIupTe | Levy Cristian | Lottie Simple License (free, no attribution required) | ~19.3 KB | An open book with pages gently turning ("página"/"página 2"/"página 3" layers, Portuguese for "page") — used as the friendly "nothing here yet" illustration for empty Library/Canvas states. Contains one small embedded PNG (170x124, base64-inlined in the JSON itself — no external network fetch needed, safe for this local-first app). |

No 5th/optional animation was added — everything found for additional
categories (e.g. a literal "firefly" or "glowing bug" character) on
LottieFiles' free tier either turned out to be a premium/IconScout-hosted
asset behind a paywall (e.g. "Firefly Animation by Graphiqa Studio"), a much
heavier multi-character scene (a "Frog catching a firefly among mushrooms"
animation, ~30-36 KB with a full illustrated frog, eyes, mushrooms, etc. —
too complex/narrative for an ambient loop and not truly a firefly asset by
itself), or grossly oversized for a small UI loop (a "Looping Energy Orb"
animation weighed in at 4.2 MB and 17.8 MB for its two variants — almost
certainly embedded raster frames — and was rejected outright per the
filesize requirement). Rather than guess at a fifth pick or stretch a
mismatched asset into the mascot slot, the glow-orb pick above was used for
the mascot idle loop and no separate 5th animation was added.

## How the sources were verified

Each pick was fetched via `curl` with a standard desktop User-Agent (LottieFiles
blocks the sandbox's `WebFetch` tool with an HTTP 403, but permits normal
`curl` requests). Each animation's own detail page on lottiefiles.com was
inspected for:
- The `"license":"https://lottiefiles.com/page/license"` field embedded in the
  page's data, confirming it is under LottieFiles' own free license (not a
  premium/IconScout-embedded item — one candidate, a "firefly" animation
  page, was excluded specifically because it turned out to be an IconScout
  premium item with a watermarked preview).
- The `og:title` meta tag, for the creator name credit shown in the table
  above.
- The raw Lottie JSON itself, fetched directly from LottieFiles' asset CDN
  (`assets-v2.lottiefiles.com`) and pretty-printed to confirm its internal
  layer names/dimensions match the animation's stated theme before saving it
  under its final filename in this repo.

## Full license text (Lottie Simple License, as published at `lottiefiles.com/page/license`, retrieved 2026-07-28)

> Permission is hereby granted, free of charge, to any person obtaining a
> copy of the public animation files available for download at the
> LottieFiles site ("Files") to download, reproduce, modify, publish,
> distribute, publicly display, and publicly digitally perform such Files,
> including for commercial purposes, provided that any display, publication,
> performance, or distribution of Files must contain (and be subject to) the
> same terms and conditions of this license. Modifications to Files are
> deemed derivative works and must also be expressly distributed under the
> same terms and conditions of this license. You may not purport to impose
> any additional or different terms or conditions on, or apply any technical
> measures that restrict exercise of, the rights granted under this license.
> This license does not include the right to collect or compile Files from
> LottieFiles to replicate or develop a similar or competing service.
>
> Use of Files without attributing the creator(s) of the Files is permitted
> under this license, though attribution is strongly encouraged. If
> attributions are included, such attributions should be visible to the end
> user.
