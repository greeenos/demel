# Demel design system

A dark, tactile “bevel” look: soft raised surfaces, inset wells and glowing accents. Everything lives in `frontend/style.css` as CSS custom properties on `:root`; light mode is only used when chosen explicitly.

## Colour

Accents are sampled from the logo gradient:

| Token | Use |
|---|---|
| `--orange` | Today, steps, strain |
| `--coral` | Health |
| `--pink` | Training |
| `--purple` | Sleep, coach |
| `--green` (mint) | Recovery, nutrition |
| `--blue` | Hydration, charts |

Surfaces are near-black graphite (`#121214` theme colour) with `--raised` and `--well` materials for buttons, pills and inputs. Status chips are tinted versions of the accent, never solid fills.

## Type and icons

- App text uses the system rounded face: `ui-rounded, "SF Pro Rounded", "Avenir Next", "Nunito Sans", system-ui`.
- The **demel** wordmark is Unbounded SemiBold (SIL OFL 1.1) converted to SVG outlines in `frontend/ui.ts`, so no font file is loaded.
- Icons are [Streamline Flex](https://www.streamlinehq.com) colour icons (CC BY 4.0), recoloured into a two-tone “duo” style in the generated `frontend/icons.ts`: the main stroke follows `currentColor`, the fill is a 24 % tint.

## Logo

`public/icon.svg` is a squircle with a mesh gradient (orange → coral → pink → periwinkle, built from blurred ellipses) and a white eight-point starburst. PNG app icons are exported with `scripts/export_icons.py`. When the logo changes, bump the `?v=` query and the service-worker cache name so installed PWAs pick it up.

## Layout

Today → Health → Food → Training → Coach. On phones a floating pill navigation sits at the bottom with a sliding indicator; on desktop a quiet sidebar shows the same items plus the last Google Health sync time. Hydration appears on Today and Food and shares one log. Cards stack in one column on phones and two columns on wide screens.

## Motion

Motion is meant to feel calm and habit-forming, never busy:

- Views rise in with a short stagger and numbers count up, but **only** on navigation, tab or day changes, never on the 60-second background refresh.
- The navigation indicator slides between items (FLIP), with a small icon bounce.
- Rings fill, bars grow and chart lines draw on entry.
- Adding water launches drops from the button into a human-figure vessel, with a splash, ripple and rising water level (`frontend/water.ts`, Web Animations API).
- Sheets slide up and fade out on close.
- Everything respects `prefers-reduced-motion`.
