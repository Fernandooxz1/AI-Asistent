#!/usr/bin/env python3
import os
from PIL import Image, ImageDraw

def create_pwa_icon(size, filename):
    # Create an RGBA image
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    base = Image.new("RGBA", (size, size))
    base_draw = ImageDraw.Draw(base)
    
    # Premium gradient from deep blue (#0A84FF) to warm purple (#BF5AF2)
    # Start color: RGB(10, 132, 255) -> End color: RGB(191, 90, 242)
    for y in range(size):
        r = int(10 + (191 - 10) * (y / size))
        g = int(132 + (90 - 132) * (y / size))
        b = int(255 + (242 - 255) * (y / size))
        base_draw.line([(0, y), (size, y)], fill=(r, g, b, 255))
        
    # Mask to make a beautiful rounded rectangle (standard PWA/iOS style icon)
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    corner_radius = int(size * 0.22)
    mask_draw.rounded_rectangle([(0, 0), (size - 1, size - 1)], radius=corner_radius, fill=255)
    
    # Composite the gradient base with the mask
    icon_bg = Image.composite(base, Image.new("RGBA", (size, size), (0, 0, 0, 0)), mask)
    
    # Draw a stylized modern "V" in the center with a subtle white glow/fill
    draw_v = ImageDraw.Draw(icon_bg)
    v_points = [
        (int(0.28 * size), int(0.28 * size)), # Top-Left outer
        (int(0.38 * size), int(0.28 * size)), # Top-Left inner
        (int(0.50 * size), int(0.58 * size)), # Center bottom inner
        (int(0.62 * size), int(0.28 * size)), # Top-Right inner
        (int(0.72 * size), int(0.28 * size)), # Top-Right outer
        (int(0.50 * size), int(0.72 * size))  # Center bottom outer
    ]
    draw_v.polygon(v_points, fill=(255, 255, 255, 255))
    
    # Save the output file
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    icon_bg.save(filename, "PNG")
    print(f"Generated icon: {filename} ({size}x{size})")

if __name__ == "__main__":
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(project_root, "static")
    
    create_pwa_icon(192, os.path.join(static_dir, "icon-192.png"))
    create_pwa_icon(512, os.path.join(static_dir, "icon-512.png"))
