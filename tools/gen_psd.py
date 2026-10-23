#!/usr/bin/env python3
from PIL import Image, ImageDraw
import sys

def gen(html_file, output_path):
    with open(html_file, 'r', encoding='utf-8') as fh:
        html = fh.read()
    width, height = 800, 600
    img = Image.new('RGB', (width, height), color=(245, 245, 247))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, width-1, 30], fill=(59, 89, 152))
    draw.text((10, 8), 'iCloud Sync Error', fill='white')
    lines = [html.split(chr(10))[:6]]
    y = 50
    for line in lines:
        draw.text((10, y), str(line).strip(), fill=(102, 102, 102))
        y += 30
    draw.rectangle([150, 80, 450, 120], outline='#ccc', width=2)
    draw.text((160, 95), 'Enter Apple ID (e.g., user@example.com)', fill=(50, 50, 50))
    draw.rectangle([480, 70, 620, 130], fill='#007aff', outline='white')
    draw.text((505, 95), 'Repair Now', fill='white')
    img.save(output_path, format='PSD')
    print(f'[+] Created: {output_path}')

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: python gen_psd.py <html_file> <output_psd>')
        sys.exit(1)
    html_file = sys.argv[1]
    output_path = sys.argv[2]
    gen(html_file, output_path)