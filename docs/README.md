# MedAxis website

Static one-page site (HTML + CSS + a little JavaScript, no build step).

- `index.html`: content
- `styles.css`: design
- `main.js`: signal animations and scroll reveals
- `assets/data/trace.js`: real breathing trace from the Kinect v2 prototype (hand-motion simulation, recording 2026-11-17)
- `assets/img/depth_hand.png`: depth frame from the same recording, with the analysis box
- `assets/team/`: team photos

## Preview locally
Double-click `index.html`, or from this folder run `python3 -m http.server` and open http://localhost:8000.

## Team photos
Save square photos as `assets/team/bobby.jpg`, `allen.jpg`, `alan.jpg`, `jessica.jpg`.
Until a photo exists, the card shows the person's initials.

## Publish with GitHub Pages
1. Commit and push the `docs/` folder to `main`.
2. On GitHub: **Settings → Pages → Build and deployment → Deploy from a branch → `main` / `/docs` → Save**.
3. After about a minute the site is live at `https://<github-username>.github.io/neonatal_respiratory_monitoring/`.
