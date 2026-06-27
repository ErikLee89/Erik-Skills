#!/usr/bin/env python3
"""Convert an authorized Doc88 preview URL to a text-selectable PDF.

This script only uses EBT resources explicitly listed in the page's m_main
configuration. It does not scan hidden pages or bypass login/captcha controls.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests
from pypdf import PdfReader, PdfWriter

from swf_xml_vector import rebuild_pdf_page_from_swf_xml


KEY_MAIN = "PJLKMNOI3xyz021wvrpqstouHCFBDEGAnhikjlmgfZbacedYRXTSUVQW!56789+4"
KEY_EBT = "PJKLMNOI3xyz012wvprqstuoHBCDEFGAnhijklmgfZabcdeYXRSTUVWQ!56789+4"
STD_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
DEFAULT_TOOLS_DIR = Path(__file__).resolve().parents[1] / ".tools"
DEFAULT_OUTPUT_ROOT = None
JRE_URL = "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jre/hotspot/normal/eclipse"
FFDEC_URL = "https://github.com/jindrapetrik/jpexs-decompiler/releases/download/version26.2.1/ffdec_26.2.1.zip"
GHOSTSCRIPT_URL = "https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/gs10071/gs10071w64.exe"
SEVENZIP_URL = "https://www.7-zip.org/a/7za920.zip"


def parse_page_set(value: str | None) -> set[int]:
    pages: set[int] = set()
    if not value:
        return pages
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            pages.update(range(int(start), int(end) + 1))
        else:
            pages.add(int(part))
    return pages


def default_downloads_dir() -> Path:
    if sys.platform.startswith("win"):
        # Prefer the user-configured Windows Downloads location. This handles
        # redirected folders such as D:\Users\<name>\Downloads.
        try:
            import os
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            value_name = "{374DE290-123F-4565-9164-39C4925E467B}"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
            path = Path(os.path.expandvars(value))
            if path:
                return path
        except Exception:
            pass
        try:
            import ctypes
            import uuid
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", ctypes.c_ulong),
                    ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort),
                    ("Data4", ctypes.c_ubyte * 8),
                ]

            raw = uuid.UUID("374DE290-123F-4565-9164-39C4925E467B").bytes_le
            folder_id = GUID.from_buffer_copy(raw)
            path_ptr = wintypes.LPWSTR()
            result = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(folder_id), 0, None, ctypes.byref(path_ptr)
            )
            if result == 0 and path_ptr.value:
                path = Path(path_ptr.value)
                ctypes.windll.ole32.CoTaskMemFree(path_ptr)
                return path
        except Exception:
            pass
    return Path.home() / "Downloads"


def decode_doc88(data: str, key: str) -> str:
    return base64.b64decode(data.translate(str.maketrans(key, STD_B64))).decode("utf-8")


def encode_doc88(data: str, key: str = KEY_EBT) -> str:
    return (
        base64.b64encode(data.encode("utf-8"))
        .decode("utf-8")
        .translate(str.maketrans(STD_B64, key))
    )


def safe_name(name: str) -> str:
    for a, b in zip('*|:?/<>"\\', "＊｜：？／＜＞＂＼"):
        name = name.replace(a, b)
    return name.strip() or "doc88_document"


def normalize_url(value: str) -> str:
    value = value.strip()
    if value.isdigit():
        return f"https://www.doc88.com/p-{value}.html"
    if "doc88.com/p-" not in value:
        raise ValueError("Input must be a doc88 p-*.html URL or numeric document ID.")
    return value


def p_code_from_url(url: str) -> str:
    match = re.search(r"/p-(\d+)\.html", url)
    if not match:
        raise ValueError("Could not find p_code in URL.")
    return match.group(1)


def fetch_config(url: str, session: requests.Session) -> dict[str, Any]:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    match = re.search(r'm_main\.init\("([^"]*)"\);', response.text)
    if not match:
        hints = ["安全验证", "登录", "验证码", "拖动", "captcha", "slider"]
        if any(h in response.text for h in hints):
            raise RuntimeError(
                "m_main.init was not found; the page appears to require login or verification. "
                "Open it in a browser with authorization, then provide accessible data or local EBT files."
            )
        raise RuntimeError("m_main.init was not found in the page HTML.")
    return json.loads(decode_doc88(match.group(1), KEY_MAIN))


def download_file(url: str, dest: Path, session: requests.Session, timeout: int = 60) -> str:
    if dest.exists() and dest.stat().st_size > 0:
        return "cached"
    response = session.get(url, timeout=timeout)
    if response.status_code != 200 or not response.content:
        raise RuntimeError(f"Download failed: HTTP {response.status_code} bytes={len(response.content or b'')} {url}")
    dest.write_bytes(response.content)
    return "ok"


def download_url(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=180) as r:
        dest.write_bytes(r.read())


def ensure_tools(tools_dir: Path, allow_download: bool) -> tuple[Path, Path]:
    java = tools_dir / "jre17" / "bin" / "java.exe"
    ffdec = tools_dir / "ffdec" / "ffdec.jar"
    if java.exists() and ffdec.exists():
        return java, ffdec
    if not allow_download:
        raise RuntimeError(f"Missing portable Java or ffdec under {tools_dir}")
    tools_dir.mkdir(parents=True, exist_ok=True)
    if not java.exists():
        print("Downloading portable Java 17...", flush=True)
        zip_path = tools_dir / "temurin17-jre.zip"
        extract_dir = tools_dir / "jre_extract"
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        download_url(JRE_URL, zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
        java_candidates = list(extract_dir.rglob("java.exe"))
        if not java_candidates:
            raise RuntimeError("java.exe not found after extracting JRE.")
        root = java_candidates[0].parent.parent
        if (tools_dir / "jre17").exists():
            shutil.rmtree(tools_dir / "jre17")
        shutil.move(str(root), str(tools_dir / "jre17"))
        shutil.rmtree(extract_dir, ignore_errors=True)
    if not ffdec.exists():
        print("Downloading ffdec 26.2.1...", flush=True)
        zip_path = tools_dir / "ffdec_26.2.1.zip"
        target = tools_dir / "ffdec"
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        download_url(FFDEC_URL, zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(target)
        jars = list(target.rglob("ffdec.jar"))
        if not jars:
            raise RuntimeError("ffdec.jar not found after extracting ffdec.")
        if jars[0] != ffdec:
            shutil.copy2(jars[0], ffdec)
    return java, ffdec


def build_ebt_jobs(cfg: dict[str, Any], out_dir: Path) -> list[tuple[str, int, str, Path]]:
    pageids = decode_doc88(cfg["pageInfo"], KEY_MAIN).split(",")
    headnums = cfg["headerInfo"].replace('"', "").split(",")
    ebt_host = cfg["ebt_host"].rstrip("/")
    p_swf = cfg["p_swf"]
    p_code = cfg["p_code"]
    jobs: list[tuple[str, int, str, Path]] = []
    for level, headnum in enumerate(headnums, 1):
        name = "getebt-" + encode_doc88(f"{level}-0-{headnum}-{p_swf}") + ".ebt"
        jobs.append(("ph", level, f"{ebt_host}/{name}", out_dir / name))
    for page, pageid in enumerate(pageids, 1):
        parts = pageid.split("-")
        level = int(parts[0])
        name = "getebt-" + encode_doc88(f"{level}-{parts[3]}-{parts[4]}-{p_swf}-{page}-{p_code}") + ".ebt"
        jobs.append(("pk", page, f"{ebt_host}/{name}", out_dir / name))
    return jobs


def download_ebt(jobs: list[tuple[str, int, str, Path]], session: requests.Session, workers: int) -> dict[str, int]:
    ok = cached = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(download_file, url, path, session) for _, _, url, path in jobs]
        for n, future in enumerate(as_completed(futures), 1):
            status = future.result()
            ok += status == "ok"
            cached += status == "cached"
            if n % 25 == 0 or n == len(jobs):
                print(f"EBT {n}/{len(jobs)} ok={ok} cached={cached}", flush=True)
    return {"ok": ok, "cached": cached, "total": len(jobs)}


def rebuild_swfs(out_dir: Path) -> int:
    swf_dir = out_dir / "swf"
    swf_dir.mkdir(exist_ok=True)
    ph: dict[int, Path] = {}
    pk: list[dict[str, Any]] = []
    for path in out_dir.glob("getebt-*.ebt"):
        parts = decode_doc88(path.stem[len("getebt-") :], KEY_EBT).split("-")
        if len(parts) == 6:
            ph[int(parts[0])] = path
        elif len(parts) == 8:
            pk.append({"level": int(parts[0]), "page": int(parts[6]), "path": path})
    pk.sort(key=lambda item: item["page"])
    if not ph or not pk:
        raise RuntimeError("Missing PH or PK EBT files.")
    for item in pk:
        ph_data = bytearray(zlib.decompress(ph[item["level"]].read_bytes()[40:]))
        pk_data = zlib.decompress(item["path"].read_bytes()[32:])
        swf = bytearray()
        swf.extend(ph_data)
        swf.extend(pk_data)
        swf.extend(struct.pack("<BBBB", 64, 0, 0, 0))
        swf[4:8] = struct.pack("<I", len(swf))
        if len(swf) > 19:
            swf[19] = 1
        (swf_dir / f"{item['page']}.swf").write_bytes(swf)
    return len(pk)

class SwfBits:
    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos
        self.bit = 0

    def align(self) -> None:
        if self.bit:
            self.pos += 1
            self.bit = 0

    def ub(self, n: int) -> int:
        if n <= 0:
            return 0
        value = 0
        for _ in range(n):
            if self.pos >= len(self.data):
                raise EOFError("SWF bitstream ended")
            byte = self.data[self.pos]
            value = (value << 1) | ((byte >> (7 - self.bit)) & 1)
            self.bit += 1
            if self.bit == 8:
                self.bit = 0
                self.pos += 1
        return value

    def sb(self, n: int) -> int:
        if n <= 0:
            return 0
        value = self.ub(n)
        sign = 1 << (n - 1)
        return value - (1 << n) if value & sign else value

    def u8(self) -> int:
        self.align()
        value = self.data[self.pos]
        self.pos += 1
        return value

    def u16(self) -> int:
        self.align()
        value = struct.unpack_from("<H", self.data, self.pos)[0]
        self.pos += 2
        return value

    def s16(self) -> int:
        self.align()
        value = struct.unpack_from("<h", self.data, self.pos)[0]
        self.pos += 2
        return value


def read_swf_rect(bits: SwfBits) -> tuple[int, int, int, int]:
    nbits = bits.ub(5)
    xmin = bits.sb(nbits)
    xmax = bits.sb(nbits)
    ymin = bits.sb(nbits)
    ymax = bits.sb(nbits)
    bits.align()
    return xmin, xmax, ymin, ymax


def read_swf_matrix(bits: SwfBits) -> dict[str, float]:
    has_scale = bits.ub(1)
    scale_x = scale_y = 1.0
    if has_scale:
        nbits = bits.ub(5)
        scale_x = bits.sb(nbits) / 65536.0
        scale_y = bits.sb(nbits) / 65536.0
    has_rotate = bits.ub(1)
    rotate0 = rotate1 = 0.0
    if has_rotate:
        nbits = bits.ub(5)
        rotate0 = bits.sb(nbits) / 65536.0
        rotate1 = bits.sb(nbits) / 65536.0
    nbits = bits.ub(5)
    translate_x = bits.sb(nbits)
    translate_y = bits.sb(nbits)
    bits.align()
    return {
        "scale_x": scale_x,
        "scale_y": scale_y,
        "rotate0": rotate0,
        "rotate1": rotate1,
        "translate_x": translate_x,
        "translate_y": translate_y,
    }


def iter_swf_tags(data: bytes, start: int) -> list[tuple[int, bytes]]:
    pos = start
    tags: list[tuple[int, bytes]] = []
    while pos + 2 <= len(data):
        code_len = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        code = code_len >> 6
        length = code_len & 0x3F
        if length == 0x3F:
            if pos + 4 > len(data):
                break
            length = struct.unpack_from("<I", data, pos)[0]
            pos += 4
        body = data[pos : pos + length]
        pos += length
        tags.append((code, body))
        if code == 0:
            break
    return tags


def read_swf(path: Path) -> tuple[tuple[int, int, int, int], list[tuple[int, bytes]]]:
    raw = path.read_bytes()
    if raw[:3] == b"CWS":
        data = b"FWS" + raw[3:8] + zlib.decompress(raw[8:])
    else:
        data = raw
    bits = SwfBits(data, 8)
    frame = read_swf_rect(bits)
    bits.u16()
    bits.u16()
    return frame, iter_swf_tags(data, bits.pos)


def parse_text2_metrics(body: bytes) -> dict[str, Any]:
    bits = SwfBits(body)
    bits.u16()
    read_swf_rect(bits)
    matrix = read_swf_matrix(bits)
    glyph_bits = bits.u8()
    advance_bits = bits.u8()
    records = glyphs = single_glyph_records = inherited_font_records = 0
    while bits.pos < len(body):
        first = bits.u8()
        if first == 0:
            break
        if first & 0x80:
            flags = first
            if flags & 0x08:
                bits.u16()
            else:
                inherited_font_records += 1
            if flags & 0x04:
                bits.pos += 4
            if flags & 0x01:
                bits.s16()
            if flags & 0x02:
                bits.s16()
            if flags & 0x08:
                bits.u16()
        else:
            count = first & 0x7F
            records += 1
            glyphs += count
            if count <= 1:
                single_glyph_records += 1
            for _ in range(count):
                bits.align()
                bits.ub(glyph_bits)
                bits.sb(advance_bits)
            bits.align()
    return {
        "matrix": matrix,
        "records": records,
        "glyphs": glyphs,
        "single_glyph_records": single_glyph_records,
        "inherited_font_records": inherited_font_records,
    }


def analyze_swf_page(path: Path) -> dict[str, Any]:
    frame, tags = read_swf(path)
    counts: dict[int, int] = {}
    for code, _ in tags:
        counts[code] = counts.get(code, 0) + 1
    inner_counts: dict[int, int] = {}
    text_metrics: list[dict[str, Any]] = []
    place_with_matrix = 0
    rotate_or_skew = 0
    bookmaker_fonts = 0

    def scan_tags(items: list[tuple[int, bytes]], nested: bool = False) -> None:
        nonlocal place_with_matrix, rotate_or_skew, bookmaker_fonts
        for code, body in items:
            if nested:
                inner_counts[code] = inner_counts.get(code, 0) + 1
            if code == 26 and body:
                flags = body[0]
                if flags & 0x01:
                    try:
                        bits = SwfBits(body, 3 + (2 if flags & 0x02 else 0))
                        matrix = read_swf_matrix(bits)
                        place_with_matrix += 1
                        if abs(matrix["rotate0"]) > 0.01 or abs(matrix["rotate1"]) > 0.01:
                            rotate_or_skew += 1
                    except Exception:
                        pass
            elif code == 33:
                try:
                    text_metrics.append(parse_text2_metrics(body))
                except Exception:
                    text_metrics.append({"parse_error": True, "records": 0, "glyphs": 0})
            elif code == 39 and len(body) >= 4:
                scan_tags(iter_swf_tags(body, 4), nested=True)
            elif code == 48:
                name_len_pos = 4
                if len(body) > name_len_pos:
                    name_len = body[name_len_pos]
                    name = body[name_len_pos + 1 : name_len_pos + 1 + name_len].decode("latin1", "ignore")
                    if "FzBookMaker" in name or "DlFont" in name:
                        bookmaker_fonts += 1

    scan_tags(tags)
    text_count = len(text_metrics)
    glyphs = sum(int(item.get("glyphs", 0)) for item in text_metrics)
    records = sum(int(item.get("records", 0)) for item in text_metrics)
    single_records = sum(int(item.get("single_glyph_records", 0)) for item in text_metrics)
    inherited_font_records = sum(int(item.get("inherited_font_records", 0)) for item in text_metrics)
    nested_text = inner_counts.get(33, 0)
    top_text = counts.get(33, 0)

    score = 0
    reasons: list[str] = []
    if nested_text >= 20 and top_text == 0:
        score += 3
        reasons.append("many_nested_text_objects")
    if text_count >= 30 and glyphs and glyphs / max(text_count, 1) <= 4:
        score += 2
        reasons.append("fragmented_text_objects")
    if records and single_records / records >= 0.35:
        score += 1
        reasons.append("many_single_glyph_records")
    if rotate_or_skew >= 5:
        score += 2
        reasons.append("rotated_or_skewed_matrices")
    if bookmaker_fonts >= 5:
        score += 1
        reasons.append("bookmaker_subset_fonts")
    if inherited_font_records >= 5:
        score += 1
        reasons.append("text_style_inheritance")
    if counts.get(39, 0) and nested_text and not top_text:
        score += 1
        reasons.append("display_list_inside_sprite")

    return {
        "page": int(path.stem),
        "swf": str(path),
        "frame_twips": frame,
        "top_tags": {str(k): v for k, v in sorted(counts.items())},
        "inner_tags": {str(k): v for k, v in sorted(inner_counts.items())},
        "text_objects": text_count,
        "text_records": records,
        "glyphs": glyphs,
        "single_glyph_records": single_records,
        "place_with_matrix": place_with_matrix,
        "rotate_or_skew_matrices": rotate_or_skew,
        "bookmaker_fonts": bookmaker_fonts,
        "inherited_font_records": inherited_font_records,
        "xml_fallback_score": score,
        "needs_swf2xml": score >= 5,
        "reasons": reasons,
    }


def analyze_swfs(out_dir: Path) -> list[dict[str, Any]]:
    swf_dir = out_dir / "swf"
    results = [analyze_swf_page(path) for path in sorted(swf_dir.glob("*.swf"), key=lambda p: int(p.stem))]
    (out_dir / "page_analysis.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    risky = [item["page"] for item in results if item["needs_swf2xml"]]
    if risky:
        print(f"SWF analysis: {len(risky)} page(s) likely need swf2xml fallback: {risky[:30]}", flush=True)
    else:
        print("SWF analysis: no high-risk pages detected for swf2xml fallback.", flush=True)
    return results

def convert_single_swf(java: Path, ffdec: Path, swf_path: Path, dest_dir: Path, zoom: float) -> tuple[int, str]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    command = [
        str(java),
        "-jar",
        str(ffdec),
        "-format",
        "frame:pdf",
        "-zoom",
        str(zoom),
        "-select",
        "1",
        "-export",
        "frame",
        str(dest_dir),
        str(swf_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    return result.returncode, (result.stderr or result.stdout)[-2000:]


def swfs_to_page_pdfs(out_dir: Path, java: Path, ffdec: Path, workers: int, zoom: float, keep_groups: bool) -> int:
    swf_dir = out_dir / "swf"
    pdf_group_root = out_dir / "pdf_groups"
    pdf_pages = out_dir / "pdf_pages"
    for path in [pdf_group_root, pdf_pages]:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
    swfs = sorted(swf_dir.glob("*.swf"), key=lambda p: int(p.stem))

    total_pages = len(swfs)
    print(f"Converting {total_pages} SWF files to PDF using {workers} workers...", flush=True)

    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(convert_single_swf, java, ffdec, swf, pdf_group_root / swf.stem, zoom): swf
            for swf in swfs
        }
        for future in as_completed(futures):
            swf = futures[future]
            rc, log = future.result()
            if rc:
                raise RuntimeError(f"ffdec conversion failed for {swf.name}:\n{log}")
            completed += 1
            if completed % 10 == 0 or completed == total_pages:
                print(f"Converted {completed}/{total_pages} pages...", flush=True)

    moved = 0
    for frames in pdf_group_root.rglob("frames.pdf"):
        parent = frames.parent.name
        if parent.isdigit():
            shutil.copy2(frames, pdf_pages / f"{parent}.pdf")
            moved += 1

    missing = [i for i in range(1, total_pages + 1) if not (pdf_pages / f"{i}.pdf").exists()]
    if missing:
        raise RuntimeError(f"Missing converted page PDFs: {missing[:20]}")
    if not keep_groups:
        shutil.rmtree(pdf_group_root, ignore_errors=True)
    return moved


def swf2xml_page(java: Path, ffdec: Path, swf: Path, xml: Path) -> tuple[int, str]:
    xml.parent.mkdir(parents=True, exist_ok=True)
    command = [str(java), "-jar", str(ffdec), "-swf2xml", str(swf), str(xml)]
    result = subprocess.run(command, capture_output=True, text=True)
    return result.returncode, (result.stderr or result.stdout)[-2000:]


def subset_fonts_in_place(pdf_path: Path) -> dict[str, Any]:
    try:
        import fitz
    except Exception as exc:
        return {"status": "skipped", "reason": f"pymupdf_unavailable:{type(exc).__name__}"}
    before = pdf_path.stat().st_size if pdf_path.exists() else 0
    tmp = pdf_path.with_suffix(pdf_path.suffix + ".subset.tmp")
    try:
        doc = fitz.open(pdf_path)
        try:
            doc.subset_fonts()
        except Exception as exc:
            subset_warning = f"subset_fonts_failed:{type(exc).__name__}"
        else:
            subset_warning = None
        doc.save(tmp, garbage=4, clean=True, deflate=True)
        doc.close()
        tmp.replace(pdf_path)
        after = pdf_path.stat().st_size
        result = {"status": "optimized", "before_bytes": before, "after_bytes": after}
        if subset_warning:
            result["warning"] = subset_warning
        return result
    except Exception as exc:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return {"status": "skipped", "reason": f"{type(exc).__name__}: {exc}", "before_bytes": before}


def apply_swf2xml_fallback_pages(out_dir: Path, java: Path, ffdec: Path, analysis: list[dict[str, Any]]) -> set[int]:
    pages = [int(item["page"]) for item in analysis if item.get("needs_swf2xml")]
    if not pages:
        return set()
    xml_dir = out_dir / "xml_pages"
    pdf_pages = out_dir / "pdf_pages"
    replacements: list[dict[str, Any]] = []
    for page in pages:
        swf = out_dir / "swf" / f"{page}.swf"
        xml = xml_dir / f"{page}.xml"
        replacement_pdf = pdf_pages / f"{page}.pdf"
        original_dir = out_dir / "pdf_pages_ffdec_original"
        original_dir.mkdir(exist_ok=True)
        original_pdf = original_dir / f"{page}.pdf"
        if replacement_pdf.exists() and not original_pdf.exists():
            shutil.copy2(replacement_pdf, original_pdf)
        rc, log = swf2xml_page(java, ffdec, swf, xml)
        if rc:
            print(f"swf2xml fallback skipped page {page}: {log}", flush=True)
            continue
        try:
            frame, _ = read_swf(swf)
            page_w = (frame[1] - frame[0]) / 20.0
            page_h = (frame[3] - frame[2]) / 20.0
            info = rebuild_pdf_page_from_swf_xml(xml, replacement_pdf, page_w, page_h)
            quality = next((item.get("pdf_text_quality", {}) for item in analysis if int(item.get("page", -1)) == page), {})
            info["hidden_text_layer"] = add_hidden_text_layer_from_pdf(replacement_pdf, original_pdf, quality) if original_pdf.exists() else {"status": "skipped", "reason": "missing_original_pdf"}
            info["page_optimization"] = subset_fonts_in_place(replacement_pdf)
            info["page"] = page
            replacements.append(info)
            print(f"swf2xml fallback replaced page {page}: glyphs={info['drawn_glyphs']} shapes={info['drawn_shapes']}", flush=True)
        except Exception as exc:
            print(f"swf2xml fallback failed page {page}: {type(exc).__name__}: {exc}", flush=True)
    (out_dir / "swf2xml_replacements.json").write_text(json.dumps(replacements, ensure_ascii=False, indent=2), encoding="utf-8")
    return {int(item["page"]) for item in replacements}


def merge_pages(out_dir: Path, title: str, page_count: int, zoom: float, unscaled_pages: set[int] | None = None) -> Path:
    pdf_pages = out_dir / "pdf_pages"
    final_pdf = unique_dest(out_dir / f"{safe_name(title)}_doc88_preview.pdf")
    writer = PdfWriter()
    unscaled_pages = unscaled_pages or set()
    for i in range(1, page_count + 1):
        reader = PdfReader(str(pdf_pages / f"{i}.pdf"))
        page = reader.pages[0]
        if zoom != 1 and i not in unscaled_pages:
            page.scale_by(1 / zoom)
        writer.add_page(page)
    with final_pdf.open("wb") as f:
        writer.write(f)
    return final_pdf


def ensure_7zip(tools_dir: Path) -> Path | None:
    local_dir = tools_dir / "7zip"
    for name in ("7za.exe", "7z.exe"):
        local = local_dir / name
        if local.exists():
            return local
    try:
        archive = tools_dir / "7za920.zip"
        download_url(SEVENZIP_URL, archive)
        if local_dir.exists():
            shutil.rmtree(local_dir)
        local_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(local_dir)
        for name in ("7za.exe", "7z.exe"):
            local = local_dir / name
            if local.exists():
                return local
        return None
    except Exception as exc:
        print(f"7-Zip portable download failed: {exc}", flush=True)
        return None


def find_7zip(tools_dir: Path | None = None) -> Path | None:
    candidates = []
    if tools_dir:
        for name in ("7za.exe", "7z.exe"):
            local = tools_dir / "7zip" / name
            if local.exists():
                candidates.append(str(local))
        downloaded = ensure_7zip(tools_dir)
        if downloaded:
            candidates.append(str(downloaded))
    candidates += [
        shutil.which("7z"),
        shutil.which("7za"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        r"D:\Program Files\7-Zip\7z.exe",
        r"D:\Program Files (x86)\7-Zip\7z.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def extract_with_7zip(archive: Path, dest: Path, tools_dir: Path) -> None:
    seven = find_7zip(tools_dir)
    if not seven:
        raise RuntimeError("7-Zip is required to extract Ghostscript without admin installation.")
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [str(seven), "x", str(archive), f"-o{dest}", "-y"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout)[-3000:])


def ensure_ghostscript(tools_dir: Path) -> Path | None:
    gs_exe = tools_dir / "ghostscript" / "bin" / "gswin64c.exe"
    if gs_exe.exists():
        return gs_exe
    if not sys.platform.startswith("win"):
        return None
    tools_dir.mkdir(parents=True, exist_ok=True)
    archive = tools_dir / "gs10071w64.exe"
    download_url(GHOSTSCRIPT_URL, archive)
    extract_with_7zip(archive, tools_dir / "ghostscript", tools_dir)
    return gs_exe if gs_exe.exists() else None


def optimize_with_ghostscript(src: Path, gs_exe: Path, pdfsettings: str = "/default") -> Path:
    dst = src.with_name(src.stem + "_gs_optimized.pdf")
    command = [
        str(gs_exe),
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.7",
        "-dNOPAUSE",
        "-dBATCH",
        "-dSAFER",
        f"-dPDFSETTINGS={pdfsettings}",
        f"-sOutputFile={dst}",
        str(src),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not dst.exists() or dst.stat().st_size == 0:
        raise RuntimeError((result.stderr or result.stdout)[-3000:])
    return dst


def optimize_with_pymupdf(src: Path) -> Path:
    try:
        import fitz
    except Exception as exc:
        raise RuntimeError("PyMuPDF is required for fallback optimization.") from exc
    dst = src.with_name(src.stem + "_vector_optimized.pdf")
    doc = fitz.open(src)
    try:
        doc.subset_fonts()
    except Exception as exc:
        print(f"PyMuPDF font subsetting skipped: {exc}", flush=True)
    doc.save(dst, garbage=4, clean=True, deflate=True)
    doc.close()
    return dst


def optimize_pdf(src: Path, tools_dir: Path, pdfsettings: str = "/default", prefer_pymupdf: bool = False) -> Path:
    if prefer_pymupdf:
        try:
            return optimize_with_pymupdf(src)
        except Exception as exc:
            print(f"PyMuPDF optimization failed; trying Ghostscript: {exc}", flush=True)
    gs_exe = ensure_ghostscript(tools_dir)
    if gs_exe and gs_exe.exists():
        try:
            return optimize_with_ghostscript(src, gs_exe, pdfsettings=pdfsettings)
        except Exception as exc:
            print(f"Ghostscript optimization failed; falling back to PyMuPDF: {exc}", flush=True)
    return optimize_with_pymupdf(src)


def find_cjk_font() -> str | None:
    if not sys.platform.startswith("win"):
        return None
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simkai.ttf",
        r"C:\Windows\Fonts\arialuni.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def add_hidden_text_layer_from_pdf(vector_pdf: Path, source_pdf: Path, quality: dict[str, Any]) -> dict[str, Any]:
    if quality.get("needs_swf2xml"):
        return {"status": "skipped", "reason": "source_text_marked_bad"}
    if int(quality.get("nonspace") or 0) == 0:
        return {"status": "skipped", "reason": "source_has_no_text"}
    try:
        import fitz
    except Exception as exc:
        return {"status": "skipped", "reason": f"pymupdf_unavailable:{type(exc).__name__}"}

    src = fitz.open(source_pdf)
    dst = fitz.open(vector_pdf)
    if not src.page_count or not dst.page_count:
        src.close()
        dst.close()
        return {"status": "skipped", "reason": "empty_pdf"}
    src_page = src[0]
    dst_page = dst[0]
    sx = dst_page.rect.width / src_page.rect.width
    sy = dst_page.rect.height / src_page.rect.height
    fontfile = find_cjk_font()
    spans = inserted = failed = 0
    data = src_page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "")
                if not text or not text.strip():
                    continue
                spans += 1
                x0, y0, x1, y1 = span.get("bbox", (0, 0, 0, 0))
                point = fitz.Point(x0 * sx, y1 * sy)
                fontsize = max(1.0, float(span.get("size", 8)) * min(sx, sy))
                try:
                    kwargs = {
                        "fontsize": fontsize,
                        "render_mode": 3,
                        "overlay": True,
                    }
                    if fontfile:
                        kwargs.update({"fontname": "doc88hidden", "fontfile": fontfile})
                    dst_page.insert_text(point, text, **kwargs)
                    inserted += 1
                except Exception:
                    failed += 1
    tmp = vector_pdf.with_suffix(vector_pdf.suffix + ".hidden.tmp")
    dst.save(tmp, garbage=4, deflate=True)
    dst.close()
    src.close()
    tmp.replace(vector_pdf)
    return {"status": "added" if inserted else "skipped", "spans": spans, "inserted": inserted, "failed": failed, "fontfile": fontfile}


def page_pdf_text_quality(pdf_path: Path) -> dict[str, Any]:
    font_names: list[str] = []
    try:
        reader = PdfReader(str(pdf_path))
        text = reader.pages[0].extract_text() or "" if reader.pages else ""
    except Exception as exc:
        return {
            "pdf": str(pdf_path),
            "extract_error": f"{type(exc).__name__}: {exc}",
            "needs_swf2xml": False,
            "visual_glyph_risk": False,
            "reasons": ["pdf_text_extract_error"],
            "visual_reasons": [],
        }
    try:
        import fitz

        doc = fitz.open(pdf_path)
        if doc.page_count:
            font_names = [str(font[3]) for font in doc[0].get_fonts(full=True)]
        doc.close()
    except Exception:
        font_names = []

    nonspace = sum(not ch.isspace() for ch in text)
    cjk = sum("\u4e00" <= ch <= "\u9fff" for ch in text)
    ascii_letters = sum("a" <= ch.lower() <= "z" for ch in text)
    digits = sum(ch.isdigit() for ch in text)
    math_symbols = sum(ch in "=+-???*/??<>??" for ch in text)
    bracket_symbols = sum(ch in "()[]{}" for ch in text)
    question = text.count("?")
    replacement = text.count("\ufffd")
    bad_common = text.count("\u793a") + text.count("\u653e")
    high_number_fonts = []
    for name in font_names:
        match = re.search(r"MYFONT(\d+)", name)
        if match and int(match.group(1)) >= 1000:
            high_number_fonts.append(name)

    reasons: list[str] = []
    visual_reasons: list[str] = []
    if nonspace >= 80 and cjk == 0 and (question + replacement) / max(nonspace, 1) >= 0.25:
        reasons.append("question_mark_text_layer")
    if nonspace >= 120 and cjk == 0 and ascii_letters <= 10 and bad_common >= 20:
        reasons.append("garbled_repeated_cjk_markers")
    if nonspace >= 120 and cjk == 0 and ascii_letters <= 10 and (question + replacement + bad_common) >= 30:
        reasons.append("no_cjk_in_large_text_layer")
    if high_number_fonts and nonspace >= 120 and digits >= 40 and (math_symbols >= 8 or bracket_symbols >= 6):
        visual_reasons.append("symbol_font_visual_glyph_risk")
    if high_number_fonts and digits >= 120 and bracket_symbols >= 4:
        visual_reasons.append("numeric_bracket_symbol_font_risk")

    return {
        "pdf": str(pdf_path),
        "chars": len(text),
        "nonspace": nonspace,
        "cjk": cjk,
        "ascii_letters": ascii_letters,
        "digits": digits,
        "math_symbols": math_symbols,
        "bracket_symbols": bracket_symbols,
        "font_names": font_names,
        "high_number_fonts": sorted(set(high_number_fonts)),
        "question_marks": question,
        "replacement_chars": replacement,
        "bad_common_markers": bad_common,
        "needs_swf2xml": bool(reasons),
        "visual_glyph_risk": bool(visual_reasons),
        "reasons": reasons,
        "visual_reasons": visual_reasons,
        "sample": text.replace("\n", " ")[:160],
    }


def add_pdf_quality_to_analysis(out_dir: Path, analysis: list[dict[str, Any]], swf2xml_mode: str) -> list[dict[str, Any]]:
    pdf_pages = out_dir / "pdf_pages"
    risky: list[int] = []
    for item in analysis:
        pdf_path = pdf_pages / f"{item['page']}.pdf"
        quality = page_pdf_text_quality(pdf_path) if pdf_path.exists() else {"needs_swf2xml": False, "visual_glyph_risk": False, "reasons": ["missing_page_pdf"], "visual_reasons": []}
        item["pdf_text_quality"] = quality
        item["static_swf2xml_candidate"] = item.pop("needs_swf2xml")
        item["static_reasons"] = item.pop("reasons")
        text_bad = bool(quality.get("needs_swf2xml"))
        visual_bad = bool(quality.get("visual_glyph_risk"))
        if swf2xml_mode == "conservative":
            item["needs_swf2xml"] = bool(item["static_swf2xml_candidate"] and text_bad)
        elif swf2xml_mode == "aggressive":
            item["needs_swf2xml"] = bool(item["static_swf2xml_candidate"] and (text_bad or visual_bad or quality.get("high_number_fonts")))
        elif swf2xml_mode == "all":
            item["needs_swf2xml"] = bool(item["static_swf2xml_candidate"])
        else:
            item["needs_swf2xml"] = bool(item["static_swf2xml_candidate"] and (text_bad or visual_bad))
        item["reasons"] = (
            item["static_reasons"]
            + [f"pdf:{reason}" for reason in quality.get("reasons", [])]
            + [f"visual:{reason}" for reason in quality.get("visual_reasons", [])]
        )
        if item["needs_swf2xml"]:
            risky.append(item["page"])
    (out_dir / "page_analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    if risky:
        print(f"PDF/SWF analysis: {len(risky)} page(s) should use swf2xml fallback: {risky[:30]}", flush=True)
    else:
        print("PDF/SWF analysis: no pages require swf2xml fallback after ffdec checks.", flush=True)
    return analysis


def verify_pdf(path: Path) -> dict[str, Any]:
    reader = PdfReader(str(path))
    text = (reader.pages[0].extract_text() or "").replace("\n", " ")[:300] if reader.pages else ""
    return {
        "path": str(path),
        "pages": len(reader.pages),
        "size_mb": round(path.stat().st_size / 1024 / 1024, 1),
        "first_text_sample": text,
    }


def unique_dest(path: Path) -> Path:
    if not path.exists():
        return path
    for i in range(1, 1000):
        candidate = path.with_name(f"{path.stem}_{i}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not find an unused output filename for {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert an authorized Doc88 URL to a text-selectable PDF.")
    parser.add_argument("url_or_id", help="Doc88 p-*.html URL or numeric document ID.")
    parser.add_argument("--output-root", default=None, help="Directory for the final PDF. Default: system Downloads folder.")
    parser.add_argument("--tools-dir", default=str(DEFAULT_TOOLS_DIR), help="Portable Java/ffdec directory.")
    parser.add_argument("--workers", type=int, default=8, help="EBT download workers.")
    parser.add_argument("--convert-workers", type=int, default=5, help="ffdec conversion workers.")
    parser.add_argument("--zoom", type=float, default=2.0, help="ffdec PDF export zoom; pages are scaled back on merge.")
    parser.add_argument("--no-optimize", action="store_true", help="Skip the default non-rasterized PDF optimization step.")
    parser.add_argument("--gs-pdfsettings", default="/default", help="Ghostscript PDFSETTINGS value, for example /default, /prepress, or /ebook.")
    parser.add_argument("--no-download-tools", action="store_true", help="Do not download portable Java/ffdec if missing.")
    parser.add_argument("--keep-intermediates", action="store_true", help="Keep EBT, SWF, page PDFs, and run_summary.json.")
    parser.add_argument("--keep-groups", action="store_true", help="Keep temporary grouped conversion folders.")
    parser.add_argument("--no-swf2xml-fallback", action="store_true", help="Do not replace detected problematic pages with swf2xml vector reconstruction.")
    parser.add_argument("--swf2xml-mode", choices=["conservative", "auto", "aggressive", "all"], default="auto", help="Fallback detection mode. auto adds high-confidence visual glyph risk checks; conservative uses only broken text layers.")
    parser.add_argument("--force-swf2xml-pages", default="", help="Comma/range list of pages to force through swf2xml fallback, for example 1,48-50.")
    parser.add_argument("--skip-swf2xml-pages", default="", help="Comma/range list of pages to keep as original ffdec PDFs even if detected.")
    args = parser.parse_args()

    url = normalize_url(args.url_or_id)
    p_code = p_code_from_url(url)
    output_root = Path(args.output_root) if args.output_root else default_downloads_dir()
    output_root.mkdir(parents=True, exist_ok=True)
    if args.keep_intermediates:
        out_dir = output_root / f"doc88_{p_code}_ebt"
    else:
        out_dir = Path(tempfile.mkdtemp(prefix=f"doc88_{p_code}_", dir=str(output_root)))
    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125 Safari/537.36",
            "Referer": "https://www.doc88.com/",
        }
    )

    start = time.time()
    java, ffdec = ensure_tools(Path(args.tools_dir), allow_download=not args.no_download_tools)
    cfg = fetch_config(url, session)
    (out_dir / "index.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    page_count = len(decode_doc88(cfg["pageInfo"], KEY_MAIN).split(","))
    print(f"Document: {cfg.get('p_name')} | pages={page_count} | p_code={cfg.get('p_code')}", flush=True)

    jobs = build_ebt_jobs(cfg, out_dir)
    ebt_summary = download_ebt(jobs, session, workers=args.workers)
    swf_count = rebuild_swfs(out_dir)
    page_analysis = analyze_swfs(out_dir)
    pdf_page_count = swfs_to_page_pdfs(
        out_dir,
        java=java,
        ffdec=ffdec,
        workers=args.convert_workers,
        zoom=args.zoom,
        keep_groups=args.keep_groups,
    )
    page_analysis = add_pdf_quality_to_analysis(out_dir, page_analysis, args.swf2xml_mode)
    force_swf2xml_pages = parse_page_set(args.force_swf2xml_pages)
    skip_swf2xml_pages = parse_page_set(args.skip_swf2xml_pages)
    for item in page_analysis:
        page_no = int(item["page"])
        if page_no in force_swf2xml_pages:
            item["needs_swf2xml"] = True
            item.setdefault("reasons", []).append("manual_force_swf2xml")
        if page_no in skip_swf2xml_pages:
            item["needs_swf2xml"] = False
            item.setdefault("reasons", []).append("manual_skip_swf2xml")
    (out_dir / "page_analysis.json").write_text(json.dumps(page_analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    swf2xml_replaced_pages: set[int] = set()
    if not args.no_swf2xml_fallback:
        swf2xml_replaced_pages = apply_swf2xml_fallback_pages(out_dir, java, ffdec, page_analysis)
    final_pdf = merge_pages(out_dir, cfg.get("p_name") or f"doc88_{p_code}", pdf_page_count, zoom=args.zoom, unscaled_pages=swf2xml_replaced_pages)
    final_info = verify_pdf(final_pdf)
    optimized_info = None
    if not args.no_optimize:
        optimized = optimize_pdf(final_pdf, Path(args.tools_dir), pdfsettings=args.gs_pdfsettings, prefer_pymupdf=bool(swf2xml_replaced_pages))
        optimized_info = verify_pdf(optimized)
    chosen_pdf = Path(optimized_info["path"]) if optimized_info else final_pdf
    final_dest = unique_dest(output_root / chosen_pdf.name)
    if chosen_pdf.resolve() != final_dest.resolve():
        shutil.copy2(chosen_pdf, final_dest)
    delivered_info = verify_pdf(final_dest)

    summary = {
        "url": url,
        "p_code": p_code,
        "title": cfg.get("p_name"),
        "out_dir": str(out_dir),
        "ebt": ebt_summary,
        "swf_count": swf_count,
        "swf2xml_candidate_pages": [item["page"] for item in page_analysis if item["needs_swf2xml"]],
        "swf2xml_replaced_pages": sorted(swf2xml_replaced_pages),
        "force_swf2xml_pages": sorted(force_swf2xml_pages),
        "swf2xml_mode": args.swf2xml_mode,
        "skip_swf2xml_pages": sorted(skip_swf2xml_pages),
        "pdf_page_count": pdf_page_count,
        "final_pdf": final_info,
        "optimized_pdf": optimized_info,
        "delivered_pdf": delivered_info,
        "seconds": round(time.time() - start, 1),
    }
    (out_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.keep_intermediates:
        shutil.rmtree(out_dir, ignore_errors=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
