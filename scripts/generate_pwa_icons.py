#!/usr/bin/env python3
import os
from PIL import Image

def create_pwa_icon_from_logo(logo_path, size, filename):
    # Load the logo image
    logo = Image.open(logo_path)
    
    # Pad to square (with transparent background)
    max_dim = max(logo.width, logo.height)
    square_img = Image.new("RGBA", (max_dim, max_dim), (0, 0, 0, 0))
    # Paste centered
    x_offset = (max_dim - logo.width) // 2
    y_offset = (max_dim - logo.height) // 2
    square_img.paste(logo, (x_offset, y_offset))
    
    # Resize to the required size using Lanczos resampling
    resized = square_img.resize((size, size), Image.Resampling.LANCZOS)
    
    # Save the output file
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    resized.save(filename, "PNG")
    print(f"Generated icon: {filename} ({size}x{size})")

def create_favicon(logo_path, filename):
    logo = Image.open(logo_path)
    max_dim = max(logo.width, logo.height)
    square_img = Image.new("RGBA", (max_dim, max_dim), (0, 0, 0, 0))
    x_offset = (max_dim - logo.width) // 2
    y_offset = (max_dim - logo.height) // 2
    square_img.paste(logo, (x_offset, y_offset))
    
    # Save as ICO with multiple standard sizes
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    square_img.save(filename, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print(f"Generated favicon: {filename}")

if __name__ == "__main__":
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logo_path = os.path.join(project_root, "viernes-logo.png")
    
    if not os.path.exists(logo_path):
        print(f"Error: {logo_path} does not exist!")
        exit(1)
        
    # Standard static directories to update
    static_dirs = [
        os.path.join(project_root, "static"),
    ]
    
    # Also update dist folder directly so it works on running app without full rebuild
    dist_static = os.path.join(project_root, "dist", "viernes", "_internal", "static")
    if os.path.exists(dist_static):
        static_dirs.append(dist_static)
        
    for static_dir in static_dirs:
        print(f"Updating icons in: {static_dir}")
        create_pwa_icon_from_logo(logo_path, 192, os.path.join(static_dir, "icon-192.png"))
        create_pwa_icon_from_logo(logo_path, 512, os.path.join(static_dir, "icon-512.png"))
        create_favicon(logo_path, os.path.join(static_dir, "favicon.ico"))
