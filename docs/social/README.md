# Social assets

| File | What it is |
|---|---|
| `h2kvm-share-card.png` / `.svg` | 1200x630 light card: README hero and the repo's Open Graph image |
| `h2kvm-share-card-dark.png` / `.svg` | Dark variant, shown to dark-theme readers via `<picture>` |
| `h2kvm-flow.svg` | README pipeline diagram (light, with a `prefers-color-scheme: dark` rule built in) |
| `h2kvm-flow-dark.svg` | The same diagram, always dark, for `<picture>` use |
| `h2kvm-pricing.jpg`, `h2kvm-vsphere-path.jpg` | Unchanged images used elsewhere |
| `build-share-cards.py` | Generates the SVG cards and restyles the flow diagrams |

## Palette

Apple-style blue and white. Light: `#ffffff` / `#f5f5f7`, ink `#1d1d1f`, secondary `#6e6e73`, hairline `#d2d2d7`,
blue `#0071e3` to `#2997ff`. Dark: `#000` / `#0b0b0f`, text `#f5f5f7`, cards `#1c1c1e`, blue `#0a84ff` to `#5eb0ff`.
Orange (`#ff6a2a`) appears once per image, as a small dot, and nowhere else. Fonts: Helvetica Neue and Menlo.

## Rebuild

```bash
python3 docs/social/build-share-cards.py docs/social
rsvg-convert -w 1200 docs/social/h2kvm-share-card.svg      -o docs/social/h2kvm-share-card.png
rsvg-convert -w 1200 docs/social/h2kvm-share-card-dark.svg -o docs/social/h2kvm-share-card-dark.png
```

`rsvg-convert` comes with librsvg (`brew install librsvg`). The script is idempotent: it only rewrites the
`<style>` block of the flow diagrams and adds the orange dot once, so the diagram's boxes and text are edited by hand
in `h2kvm-flow.svg` and the dark copy is regenerated from it.

## GitHub Social preview

The repository's Social preview image (shown when the repo URL is shared) is not settable through the API. Upload
`docs/social/h2kvm-share-card.png` by hand under Settings, Social preview.

Copy follows the project README. The licence line reads "Zyvor Production License"; see `LICENSE`.
