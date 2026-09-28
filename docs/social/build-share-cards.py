# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: LicenseRef-Zyvor-Production-1.0
"""Generate the h2kvm share cards (light + dark) and restyle the README flow diagram.

    python3 docs/social/build-share-cards.py docs/social
    rsvg-convert -w 1200 docs/social/h2kvm-share-card.svg      -o docs/social/h2kvm-share-card.png
    rsvg-convert -w 1200 docs/social/h2kvm-share-card-dark.svg -o docs/social/h2kvm-share-card-dark.png

Writes h2kvm-share-card.svg / -dark.svg, and rewrites the <style> block of
h2kvm-flow.svg (adaptive: light, dark via prefers-color-scheme) plus
h2kvm-flow-dark.svg (always dark). The flow diagram's boxes and text are left
untouched; only its palette changes. Orange (#ff6a2a) appears exactly once per image.
"""
import re
import sys
from pathlib import Path

LIGHT = dict(
    bg0="#ffffff", bg1="#f5f5f7", wash_op="0.10", wash2_op="0.05",
    ink="#1d1d1f", sec="#6e6e73", card="#ffffff", card_stroke="#d2d2d7", shadow_op="0.10",
    blue0="#0071e3", blue1="#2997ff", link="#0071e3", wire="#0071e3", hub_sub="#dcecff",
    chip_fill="#e8f2ff", chip_stroke="#b9d8fb", hair="#e5e5ea")
DARK = dict(
    bg0="#000000", bg1="#0b0b0f", wash_op="0.20", wash2_op="0.08",
    ink="#f5f5f7", sec="#a1a1a6", card="#1c1c1e", card_stroke="#3a3a3c", shadow_op="0.55",
    blue0="#0a84ff", blue1="#5eb0ff", link="#2997ff", wire="#2997ff", hub_sub="#d6e9ff",
    chip_fill="#0b2340", chip_stroke="#1d4f8a", hair="#2c2c2e")

SANS = "'Helvetica Neue',Helvetica,Arial,sans-serif"
MONO = "'Menlo','JetBrains Mono',monospace"

# Facts come from README.md / docs/social/h2kvm-flow.svg.
SOURCES = [("vSphere", "govc · datastore"), ("ESXi", "ssh stream"),
           ("Azure", "az snapshot"), ("Files", "VMDK · VHDX · OVA")]
TARGETS = [("KubeVirt", "Zorvia · Zeus OS"), ("libvirt", "Machina"), ("OpenStack", "Glance · Nova")]
CHIPS = [("GUESTKIT", 122), ("KUBERNETES", 142), ("OFFLINE", 108)]


def pill(x, cy, w, name, sub, p):
    y = cy - 28
    return (f'<rect x="{x}" y="{y}" width="{w}" height="56" rx="15" fill="{p["card"]}" '
            f'stroke="{p["card_stroke"]}" filter="url(#shadow)"/>\n'
            f'    <text x="{x + 18}" y="{cy - 3}" font-family="{SANS}" font-size="20" font-weight="700" '
            f'fill="{p["ink"]}">{name}</text>\n'
            f'    <text x="{x + 18}" y="{cy + 16}" font-family="{MONO}" font-size="12" '
            f'fill="{p["sec"]}">{sub}</text>')


def share_card(p, dark):
    src_x, src_w = 572, 152
    hub_x, hub_w, hub_cy = 780, 140, 315
    dst_x, dst_w = 984, 144
    src_cy = [195, 275, 355, 435]
    dst_cy = [215, 315, 415]
    wires, dots, pills = [], [], []
    for cy in src_cy:
        x0, x1 = src_x + src_w, hub_x
        wires.append(f'<path d="M{x0} {cy} C {x0 + 30} {cy}, {x1 - 30} {hub_cy}, {x1} {hub_cy}"/>')
        dots.append(f'<circle cx="{x0}" cy="{cy}" r="4.5"/>')
    for cy in dst_cy:
        x0, x1 = hub_x + hub_w, dst_x
        wires.append(f'<path d="M{x0} {hub_cy} C {x0 + 32} {hub_cy}, {x1 - 32} {cy}, {x1} {cy}"/>')
        dots.append(f'<circle cx="{x1}" cy="{cy}" r="4.5"/>')
    for cy, (n, s) in zip(src_cy, SOURCES):
        pills.append(pill(src_x, cy, src_w, n, s, p))
    for cy, (n, s) in zip(dst_cy, TARGETS):
        pills.append(pill(dst_x, cy, dst_w, n, s, p))
    chips, cx = [], 72
    for label, w in CHIPS:
        chips.append(f'<rect x="{cx}" y="486" width="{w}" height="40" rx="20" fill="{p["chip_fill"]}" '
                     f'stroke="{p["chip_stroke"]}"/>\n'
                     f'    <text x="{cx + w / 2}" y="511" text-anchor="middle" font-family="{MONO}" '
                     f'font-size="14" font-weight="700" letter-spacing="1" fill="{p["link"]}">{label}</text>')
        cx += w + 12
    hub_y = hub_cy - 56
    return f'''<!-- Copyright (c) 2026 ZyvorAI Labs Private Limited. -->
<!-- SPDX-License-Identifier: LicenseRef-Zyvor-Production-1.0 -->
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-label="h2kvm — Any hypervisor to KVM. Convert offline, fix the guest, deploy with confidence. vSphere, ESXi, Azure and files in; KubeVirt, libvirt and OpenStack out.">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="630" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{p["bg0"]}"/>
      <stop offset="1" stop-color="{p["bg1"]}"/>
    </linearGradient>
    <radialGradient id="wash" cx="860" cy="300" r="520" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#0071e3" stop-opacity="{p["wash_op"]}"/>
      <stop offset="0.6" stop-color="#0071e3" stop-opacity="{p["wash2_op"]}"/>
      <stop offset="1" stop-color="#0071e3" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="blue" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{p["blue0"]}"/>
      <stop offset="1" stop-color="{p["blue1"]}"/>
    </linearGradient>
    <linearGradient id="blueText" x1="72" y1="0" x2="470" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{p["blue0"]}"/>
      <stop offset="1" stop-color="{p["blue1"]}"/>
    </linearGradient>
    <filter id="shadow" x="-20%" y="-30%" width="140%" height="190%" color-interpolation-filters="sRGB">
      <feGaussianBlur in="SourceAlpha" stdDeviation="8"/>
      <feOffset dy="7" result="b"/>
      <feColorMatrix in="b" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 {p["shadow_op"]} 0" result="s"/>
      <feMerge><feMergeNode in="s"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="glow" x="-30%" y="-40%" width="160%" height="200%" color-interpolation-filters="sRGB">
      <feGaussianBlur in="SourceAlpha" stdDeviation="13"/>
      <feOffset dy="11" result="b"/>
      <feColorMatrix in="b" type="matrix" values="0 0 0 0 0.0  0 0 0 0 0.35  0 0 0 0 0.9  0 0 0 0.30 0" result="s"/>
      <feMerge><feMergeNode in="s"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>

  <rect width="1200" height="630" fill="url(#bg)"/>
  <rect width="1200" height="630" fill="url(#wash)"/>

  <!-- Zyvor mark (blue) -->
  <rect x="72" y="56" width="56" height="56" rx="13" fill="url(#blue)"/>
  <path d="M86.5 70 113.5 70 86.5 98 113.5 98" fill="none" stroke="#ffffff" stroke-width="7"
        stroke-linecap="round" stroke-linejoin="round"/>

  <!-- eyebrow, wordmark, tagline -->
  <text x="72" y="176" font-family="{MONO}" font-size="20" font-weight="700" letter-spacing="4" fill="{p["link"]}">HYPERVISOR EXIT</text>
  <text x="68" y="296" font-family="{SANS}" font-size="132" font-weight="700" letter-spacing="-4" fill="{p["ink"]}">h2kvm</text>
  <text x="72" y="352" font-family="{SANS}" font-size="42" font-weight="600" letter-spacing="-0.8" fill="url(#blueText)">Any hypervisor to KVM.</text>
  <g font-family="{SANS}" font-size="26" fill="{p["sec"]}">
    <text x="72" y="404">Convert offline. Fix the guest.</text>
    <text x="72" y="440">Deploy with confidence.</text>
  </g>

  <!-- chips -->
  <g>
    {chips[0]}
    {chips[1]}
    {chips[2]}
  </g>

  <!-- sources -> h2kvm -> targets -->
  <text x="{src_x}" y="140" font-family="{MONO}" font-size="13" font-weight="700" letter-spacing="3" fill="{p["sec"]}">SOURCES</text>
  <text x="{dst_x}" y="140" font-family="{MONO}" font-size="13" font-weight="700" letter-spacing="3" fill="{p["sec"]}">TARGETS</text>
  <g fill="none" stroke="{p["wire"]}" stroke-opacity="0.55" stroke-width="2.5" stroke-linecap="round">
    {chr(10).join("    " + w for w in wires).strip()}
  </g>
  <g fill="{p["wire"]}">
    {chr(10).join("    " + d for d in dots).strip()}
  </g>
  <g>
    {chr(10).join("    " + q for q in pills).strip()}
  </g>
  <rect x="{hub_x}" y="{hub_y}" width="{hub_w}" height="112" rx="26" fill="url(#blue)" filter="url(#glow)"/>
  <rect x="{hub_x}" y="{hub_y}" width="{hub_w}" height="112" rx="26" fill="none" stroke="#ffffff" stroke-opacity="0.25"/>
  <text x="{hub_x + hub_w / 2}" y="{hub_cy - 2}" text-anchor="middle" font-family="{SANS}" font-size="32" font-weight="700" fill="#ffffff">h2kvm</text>
  <text x="{hub_x + hub_w / 2}" y="{hub_cy + 24}" text-anchor="middle" font-family="{MONO}" font-size="14" fill="{p["hub_sub"]}">offline repair</text>
  <!-- the single orange accent -->
  <circle cx="{hub_x + hub_w - 20}" cy="{hub_y + 20}" r="6" fill="#ff6a2a"/>

  <!-- footer -->
  <line x1="72" y1="552" x2="1128" y2="552" stroke="{p["hair"]}"/>
  <text x="72" y="592" font-family="{MONO}" font-size="18" fill="{p["sec"]}">github.com/zyvorai/h2kvm</text>
  <text x="1128" y="592" text-anchor="end" font-family="{SANS}" font-size="16" fill="{p["sec"]}">Zyvor Production License</text>
</svg>
'''


FLOW_LIGHT = dict(
    bg="#ffffff", bgs="#d2d2d7", box="#f5f5f7", boxs="#d2d2d7", hot="#eaf3ff", hots="#0071e3",
    ext="#b0b0b5", ln="#86868b", ink="#1d1d1f", sec="#6e6e73", chip="#0071e3", chipt="#ffffff")
FLOW_DARK = dict(
    bg="#000000", bgs="#3a3a3c", box="#1c1c1e", boxs="#3a3a3c", hot="#0b2340", hots="#2997ff",
    ext="#48484a", ln="#8e8e93", ink="#f5f5f7", sec="#a1a1a6", chip="#0a84ff", chipt="#ffffff")


def flow_rules(f):
    return (f"    text {{ fill: {f['ink']}; }}\n"
            f"    .bg {{ fill: {f['bg']}; stroke: {f['bgs']}; }}\n"
            f"    .box {{ fill: {f['box']}; stroke: {f['boxs']}; }}\n"
            f"    .hot {{ fill: {f['hot']}; stroke: {f['hots']}; }}\n"
            f"    .ext {{ stroke: {f['ext']}; }}\n"
            f"    .ln, .lnd {{ stroke: {f['ln']}; }}\n"
            f"    .div {{ stroke: {f['boxs']}; }}\n"
            f"    .ah {{ fill: {f['ln']}; }}\n"
            f"    .chip {{ fill: {f['chip']}; }}\n"
            f"    .chipt {{ fill: {f['chipt']}; }}\n"
            f"    .d, .m, .lbl, .hdr, .chipxt {{ fill: {f['sec']}; }}\n"
            f"    .chipx {{ stroke: {f['sec']}; }}\n")


FLOW_BASE = '''    text { font-family: "Helvetica Neue", -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }
    .box { stroke-width: 1.2; }
    .hot { stroke-width: 2; }
    .ext { fill: none; stroke-width: 1.2; stroke-dasharray: 5 4; }
    .ln { stroke-width: 1.5; fill: none; }
    .lnd { stroke-width: 1.5; fill: none; stroke-dasharray: 4 4; }
    .div { stroke-width: 1; }
    .t { font-size: 13px; font-weight: 700; }
    .d { font-size: 11px; }
    .m { font-family: Menlo, ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 10.5px; }
    .lbl { font-size: 11px; }
    .hdr { font-size: 11px; font-weight: 700; letter-spacing: 1.2px; }
    .chipt { font-size: 11px; font-weight: 700; text-anchor: middle; }
    .chipx { fill: none; stroke-width: 1.2; stroke-dasharray: 4 3; }
    .chipxt { font-size: 11px; text-anchor: middle; }
'''
DOT_MARK = "<!-- accent -->"
DOT = f'  {DOT_MARK}<circle cx="552" cy="254" r="4.5" fill="#ff6a2a"/>\n'


def restyle_flow(src, dark_only):
    style = "  <style>\n" + FLOW_BASE
    if dark_only:
        style += flow_rules(FLOW_DARK)
    else:
        style += flow_rules(FLOW_LIGHT)
        style += "    @media (prefers-color-scheme: dark) {\n"
        style += "".join("  " + l + "\n" for l in flow_rules(FLOW_DARK).rstrip("\n").split("\n"))
        style += "    }\n"
    style += "  </style>"
    out = re.sub(r"  <style>.*?</style>", lambda m: style, src, count=1, flags=re.S)
    if DOT_MARK not in out:
        anchor = '<text class="t" x="324" y="256">3 · Repair offline (GuestKit)</text>\n'
        assert anchor in out, "flow SVG anchor for the accent dot not found"
        out = out.replace(anchor, anchor + DOT, 1)
    return out


def main(outdir):
    out = Path(outdir)
    (out / "h2kvm-share-card.svg").write_text(share_card(LIGHT, False))
    (out / "h2kvm-share-card-dark.svg").write_text(share_card(DARK, True))
    flow = out / "h2kvm-flow.svg"
    src = flow.read_text()
    flow.write_text(restyle_flow(src, dark_only=False))
    (out / "h2kvm-flow-dark.svg").write_text(restyle_flow(src, dark_only=True))
    print("wrote share cards and flow diagrams in", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs/social")
