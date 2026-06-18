# -*- coding: utf-8 -*-
"""
get_cover.py - Part of the html-to-pdf skill.
Downloads a high-resolution cover image for a book from Douban (primary) or JD.com (fallback).

Usage:
  python get_cover.py --title "书名" [--output "path/to/cover.jpg"]
"""

import sys
import asyncio
import argparse
import json
import re
import shutil
import subprocess
import urllib.parse
from pathlib import Path
import requests


def _curl_fetch(url: str, headers: dict) -> bytes:
    curl = shutil.which('curl.exe') or shutil.which('curl')
    if not curl:
        return b''
    command = [curl, '-L', '--fail', '--silent', '--show-error']
    for name, value in headers.items():
        command.extend(['-H', f'{name}: {value}'])
    command.append(url)
    result = subprocess.run(command, capture_output=True, check=False)
    return result.stdout if result.returncode == 0 else b''

async def download_cover(book_title: str, output_path: Path, isbn: str = '') -> bool:
    from playwright.async_api import async_playwright
    search_title = book_title.split('：')[0].split(':')[0].strip()
    print(f'[*] Searching cover for: "{search_title}" ...')

    headers = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 Chrome/126.0 Safari/537.36'),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    for query_text in [search_title] + ([isbn] if isbn else []):
        query = urllib.parse.quote(query_text)
        douban_url = (
            'https://search.douban.com/book/subject_search?'
            f'search_text={query}&cat=1001'
        )
        print(f'[*] Searching Douban: {douban_url}')
        try:
            resp = requests.get(douban_url, headers=headers, timeout=20)
            resp.raise_for_status()
            data_match = re.search(r'window\.__DATA__\s*=\s*(\{.*?\});', resp.text, re.DOTALL)
            if not data_match:
                curl_html = _curl_fetch(douban_url, headers).decode('utf-8', errors='replace')
                data_match = re.search(
                    r'window\.__DATA__\s*=\s*(\{.*?\});', curl_html, re.DOTALL
                )
            if not data_match:
                continue
            items = json.loads(data_match.group(1)).get('items', [])
            normalized_title = re.sub(r'\s+', '', search_title)
            item = next(
                (candidate for candidate in items
                 if re.sub(r'\s+', '', candidate.get('title', '')) == normalized_title),
                items[0] if items else None,
            )
            if not item or not item.get('cover_url'):
                continue
            book_url = item.get('url', '')
            hd_url = item['cover_url'].replace('/s/', '/l/').replace('/m/', '/l/')
            image_headers = dict(headers)
            image_headers['Accept'] = 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8'
            if book_url:
                image_headers['Referer'] = book_url
            image_bytes = b''
            try:
                image_resp = requests.get(hd_url, headers=image_headers, timeout=20)
                if image_resp.ok:
                    image_bytes = image_resp.content
            except Exception:
                pass
            if len(image_bytes) <= 1000:
                image_bytes = _curl_fetch(hd_url, image_headers)
            if len(image_bytes) > 1000:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(image_bytes)
                print(f'[OK] Cover saved to: {output_path}')
                return True
        except Exception as e:
            print(f'[WARNING] Douban search failed for {query_text}: {e}')
    
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            queries = [search_title] + ([isbn] if isbn else [])
            for query_text in queries:
                query = urllib.parse.quote(query_text)
                douban_url = (
                    'https://search.douban.com/book/subject_search?'
                    f'search_text={query}&cat=1001'
                )
                print(f'[*] Searching Douban with browser: {douban_url}')
                await page.goto(douban_url, wait_until='domcontentloaded', timeout=30000)
                data_match = re.search(
                    r'window\.__DATA__\s*=\s*(\{.*?\});',
                    await page.content(),
                    re.DOTALL,
                )
                if not data_match:
                    continue
                items = json.loads(data_match.group(1)).get('items', [])
                normalized_title = re.sub(r'\s+', '', search_title)
                item = next(
                    (candidate for candidate in items
                     if re.sub(r'\s+', '', candidate.get('title', '')) == normalized_title),
                    items[0] if items else None,
                )
                if not item or not item.get('cover_url'):
                    continue
                book_url = item.get('url', '')
                hd_url = item['cover_url'].replace('/s/', '/l/').replace('/m/', '/l/')
                image_resp = await page.context.request.get(
                    hd_url, headers={'Referer': book_url, 'Accept': 'image/*'}
                )
                image_bytes = await image_resp.body()
                if image_resp.ok and len(image_bytes) > 1000:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(image_bytes)
                    print(f'[OK] Cover saved to: {output_path}')
                    await browser.close()
                    return True
            
            # Step 1: Search Douban Book
            query = urllib.parse.quote(search_title)
            douban_url = f'https://search.douban.com/book/subject_search?search_text={query}&cat=1001'
            print(f'[*] Searching Douban: {douban_url}')
            await page.goto(douban_url, wait_until='domcontentloaded', timeout=30000)
            
            item_selector = '.item-root a'
            try:
                await page.wait_for_selector(item_selector, timeout=8000)
                href = await page.get_attribute(item_selector, 'href')
            except Exception:
                href = None
                
            if href:
                print(f'[*] Found Douban book page: {href}')
                await page.goto(href, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_selector('#mainpic img', timeout=10000)
                img_url = await page.get_attribute('#mainpic img', 'src')
                if img_url:
                    hd_url = img_url.replace('/s/', '/l/')
                    print(f'[*] Downloading from Douban CDN: {hd_url}')
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    resp = requests.get(hd_url, headers=headers, timeout=15)
                    if resp.status_code == 200 and len(resp.content) > 1000:
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        output_path.write_bytes(resp.content)
                        print(f'[OK] Cover saved to: {output_path}')
                        await browser.close()
                        return True
            
            # Step 2: Fallback to JD.com Search
            jd_url = f'https://search.jd.com/Search?keyword={query}'
            print(f'[*] Fallback: Searching JD.com: {jd_url}')
            await page.goto(jd_url, wait_until='domcontentloaded', timeout=30000)
            
            img_selector = '.p-img img'
            try:
                await page.wait_for_selector(img_selector, timeout=8000)
                img_url = await page.get_attribute(img_selector, 'data-lazy-img')
                if not img_url:
                    img_url = await page.get_attribute(img_selector, 'src')
            except Exception:
                img_url = None
                
            if img_url:
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                hd_url = re.sub(r's\d+x\d+_', 's800x800_', img_url)
                hd_url = re.sub(r'n\d+/', 'n1/', hd_url)
                print(f'[*] Downloading from JD CDN: {hd_url}')
                headers = {'User-Agent': 'Mozilla/5.0'}
                resp = requests.get(hd_url, headers=headers, timeout=15)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(resp.content)
                    print(f'[OK] Cover saved to: {output_path}')
                    await browser.close()
                    return True
                    
            print('[ERROR] Cover image not found in Douban or JD search results.')
            await browser.close()
        except Exception as e:
            print(f'[ERROR] Fetch failed: {e}')
    return False

def main():
    parser = argparse.ArgumentParser(description='Download book cover from Douban or JD')
    parser.add_argument('--title', required=True, help='Book title to search')
    parser.add_argument('--isbn', default='', help='ISBN fallback for exact Douban search')
    parser.add_argument('--output', default='', help='Output JPG path (optional)')
    args = parser.parse_args()
    
    # Sanitize title for filename
    def sanitize_filename(name: str) -> str:
        return re.sub(r'[\\/*?:"<>|：]', '_', name)
        
    out_path = Path(args.output) if args.output else Path.cwd() / f"{sanitize_filename(args.title)}_封面.jpg"
    
    success = asyncio.run(download_cover(args.title, out_path, args.isbn))
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
