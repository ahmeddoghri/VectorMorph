# VectorMorph

Figma's animation export is a rigged coin flip. Some days you get a clean GIF. Most days you get a watermark, a frame-order bug, or a paywall. VectorMorph is the two-hour Flask app I built instead: feed it a folder of SVG frames, get back a clean animated WebP or GIF, in the exact order you gave it.

## What it does

Convert a stack of SVG files into a single animated WebP or GIF, with two ways to smooth the motion:

- **Frame blending**, which merges adjacent frames so the transition doesn't look like a slideshow.
- **Fade transitions**, for a gradual crossfade instead of a hard cut.

You control frame duration, background color (including transparency), blend amount, and fade steps. Upload order is preserved exactly, because an animation converter that scrambles your frames isn't a converter, it's a random number generator with extra steps.

## Install

```bash
git clone https://github.com/ahmeddoghri/VectorMorph.git
cd VectorMorph
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Run it

```bash
python app.py
```

Open `http://localhost:5001`, upload your SVG frames in order, pick your settings, and hit Convert. You'll get live progress over WebSockets instead of a spinner that might be lying to you.

## How it works

Three real steps, no hidden ones:

1. **CairoSVG** rasterizes each SVG frame to PNG.
2. **Pillow** handles the frame blending and fade transitions between them.
3. **Flask-SocketIO** streams progress back to the browser while it runs.

## Project structure

```
/vectormorph
├── static/
│   ├── assets/frames.svg   # UI background, swap it for your own
│   └── converted/          # Output files land here
├── templates/               # Upload page, results page
├── logs/app.log             # Errors, timestamped, readable
├── utils/
│   ├── image_processing.py  # Blending and fading
│   └── file_utils.py        # File handling
├── app.py                   # Main Flask app
├── config.py                # Settings
└── requirements.txt
```

## Stack

Python 3.8+, Flask, Flask-SocketIO, Pillow, CairoSVG, NumPy. No database, no cloud dependency, no account required.

## Errors and logs

Everything gets logged to `logs/app.log` with a timestamp, so when something breaks you get a real error instead of a spinning wheel:

```
2025-02-01 19:09:56,869 - ERROR - Conversion error: name 'url_for' is not defined
```

## License

MIT. See LICENSE.

## Contributing

Fork it, branch it, PR it. If you fix something that annoyed you, it probably annoyed someone else too.
