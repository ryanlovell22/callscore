"""
Generate 4 text-overlay ad images from dashboard-preview.png.

Each variation gets:
- Semi-transparent dark bar across the top (~180px)
- Bold white headline text
- Small "calloutcome.com" watermark bottom-right

Usage:
    python scripts/create_ad_images_2026-03-09.py
"""
import os
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(BASE_DIR, "app", "static", "dashboard-preview.png")
OUTPUT_DIR = os.path.join(BASE_DIR, "marketing")

VARIATIONS = [
    ("ad-image-social-proof.png", "500+ Calls Scored. 0 Hours Listening."),
    ("ad-image-ai-scores.png", "AI Scores Every Call. You Just Read the Dashboard."),
    ("ad-image-know-bookings.png", "Know Which Calls Booked Jobs — Without Listening."),
    ("ad-image-partner-proof.png", "Your Partners Can See Proof. No Login Needed."),
]

WATERMARK_TEXT = "calloutcome.com"


def load_fonts(img_width):
    """Load headline and watermark fonts, scaling to image width."""
    # Target: ~72-80pt for a 2220px wide image
    headline_size = max(48, int(img_width * 0.033))
    watermark_size = max(24, int(img_width * 0.016))

    try:
        headline_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", headline_size)
    except (OSError, IOError):
        try:
            headline_font = ImageFont.truetype("Arial", headline_size)
        except (OSError, IOError):
            headline_font = ImageFont.load_default()

    try:
        watermark_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", watermark_size)
    except (OSError, IOError):
        watermark_font = headline_font

    return headline_font, watermark_font


def create_overlay(source_path, output_path, headline_text):
    """Create a single text-overlay variation."""
    img = Image.open(source_path).convert("RGBA")
    width, height = img.size

    headline_font, watermark_font = load_fonts(width)

    # Create overlay layer
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # --- Top bar: semi-transparent dark ---
    bar_height = int(height * 0.105)  # ~180px on 1710px image
    bar_padding_top = int(bar_height * 0.15)
    draw.rectangle([(0, 0), (width, bar_height)], fill=(0, 0, 0, 200))

    # --- Headline text (centred in bar) ---
    bbox = draw.textbbox((0, 0), headline_text, font=headline_font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    text_x = (width - text_width) // 2
    text_y = bar_padding_top + (bar_height - bar_padding_top - text_height) // 2
    draw.text((text_x, text_y), headline_text, fill=(255, 255, 255, 255), font=headline_font)

    # --- Watermark: bottom-right ---
    wm_bbox = draw.textbbox((0, 0), WATERMARK_TEXT, font=watermark_font)
    wm_width = wm_bbox[2] - wm_bbox[0]
    wm_height = wm_bbox[3] - wm_bbox[1]
    wm_margin = int(width * 0.015)
    wm_x = width - wm_width - wm_margin
    wm_y = height - wm_height - wm_margin

    # Subtle background behind watermark
    wm_pad = 8
    draw.rectangle(
        [(wm_x - wm_pad, wm_y - wm_pad), (wm_x + wm_width + wm_pad, wm_y + wm_height + wm_pad)],
        fill=(0, 0, 0, 140),
    )
    draw.text((wm_x, wm_y), WATERMARK_TEXT, fill=(255, 255, 255, 200), font=watermark_font)

    # Composite and save as RGB PNG
    result = Image.alpha_composite(img, overlay).convert("RGB")
    result.save(output_path, "PNG", optimize=True)
    print(f"Created: {output_path}")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for filename, text in VARIATIONS:
        output_path = os.path.join(OUTPUT_DIR, filename)
        create_overlay(SOURCE, output_path, text)

    print(f"\nDone — {len(VARIATIONS)} images created in {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
