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


KEY_MAIN = "PJLKMNOI3xyz021wvrpqstouHCFBDEGAnhikjlmgfZbacedYRXTSUVQW!56789+4"
KEY_EBT = "PJKLMNOI3xyz012wvprqstuoHBCDEFGAnhijklmgfZabcdeYXRSTUVWQ!56789+4"
STD_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
DEFAULT_TOOLS_DIR = Path(__file__).resolve().parents[1] / ".tools"
DEFAULT_OUTPUT_ROOT = None
JRE_URL = "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jre/hotspot/normal/eclipse"
FFDEC_URL = "https://github.com/jindrapetrik/jpexs-decompiler/releases/download/version26.2.1/ffdec_26.2.1.zip"
GHOSTSCRIPT_URL = "https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/gs10071/gs10071w64.exe"


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


def convert_group(java: Path, ffdec: Path, source: Path, dest: Path, zoom: float) -> tuple[int, str]:
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
        str(dest),
        str(source),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    return result.returncode, (result.stderr or result.stdout)[-2000:]


def swfs_to_page_pdfs(out_dir: Path, java: Path, ffdec: Path, workers: int, zoom: float, keep_groups: bool) -> int:
    swf_dir = out_dir / "swf"
    group_root = out_dir / "swf_groups"
    pdf_group_root = out_dir / "pdf_groups"
    pdf_pages = out_dir / "pdf_pages"
    for path in [group_root, pdf_group_root, pdf_pages]:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
    for i in range(workers):
        (group_root / str(i)).mkdir()
        (pdf_group_root / str(i)).mkdir()
    swfs = sorted(swf_dir.glob("*.swf"), key=lambda p: int(p.stem))
    for idx, swf in enumerate(swfs):
        shutil.copy2(swf, group_root / str(idx % workers) / swf.name)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(convert_group, java, ffdec, group_root / str(i), pdf_group_root / str(i), zoom)
            for i in range(workers)
        ]
        for future in as_completed(futures):
            rc, log = future.result()
            if rc:
                raise RuntimeError(f"ffdec conversion failed:\n{log}")
    moved = 0
    for frames in pdf_group_root.rglob("frames.pdf"):
        parent = frames.parent.name
        stem = parent[:-4] if parent.endswith(".swf") else parent
        if stem.isdigit():
            shutil.copy2(frames, pdf_pages / f"{stem}.pdf")
            moved += 1
    missing = [i for i in range(1, len(swfs) + 1) if not (pdf_pages / f"{i}.pdf").exists()]
    if missing:
        raise RuntimeError(f"Missing converted page PDFs: {missing[:20]}")
    if not keep_groups:
        shutil.rmtree(group_root, ignore_errors=True)
        shutil.rmtree(pdf_group_root, ignore_errors=True)
    return moved


def merge_pages(out_dir: Path, title: str, page_count: int, zoom: float) -> Path:
    pdf_pages = out_dir / "pdf_pages"
    final_pdf = out_dir / f"{safe_name(title)}_doc88_preview.pdf"
    writer = PdfWriter()
    for i in range(1, page_count + 1):
        reader = PdfReader(str(pdf_pages / f"{i}.pdf"))
        page = reader.pages[0]
        if zoom != 1:
            page.scale_by(1 / zoom)
        writer.add_page(page)
    with final_pdf.open("wb") as f:
        writer.write(f)
    return final_pdf


def find_7zip() -> Path | None:
    candidates = [
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


def extract_with_7zip(archive: Path, dest: Path) -> None:
    seven = find_7zip()
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
    extract_with_7zip(archive, tools_dir / "ghostscript")
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
    doc.save(
        dst,
        garbage=4,
        clean=True,
        deflate=True,
        deflate_images=True,
        deflate_fonts=True,
        use_objstms=1,
        compression_effort=9,
    )
    doc.close()
    return dst


def optimize_pdf(src: Path, tools_dir: Path, pdfsettings: str = "/default") -> Path:
    gs_exe = ensure_ghostscript(tools_dir)
    if gs_exe and gs_exe.exists():
        try:
            return optimize_with_ghostscript(src, gs_exe, pdfsettings=pdfsettings)
        except Exception as exc:
            print(f"Ghostscript optimization failed; falling back to PyMuPDF: {exc}", flush=True)
    return optimize_with_pymupdf(src)


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
    pdf_page_count = swfs_to_page_pdfs(
        out_dir,
        java=java,
        ffdec=ffdec,
        workers=args.convert_workers,
        zoom=args.zoom,
        keep_groups=args.keep_groups,
    )
    final_pdf = merge_pages(out_dir, cfg.get("p_name") or f"doc88_{p_code}", pdf_page_count, zoom=args.zoom)
    final_info = verify_pdf(final_pdf)
    optimized_info = None
    if not args.no_optimize:
        optimized = optimize_pdf(final_pdf, Path(args.tools_dir), pdfsettings=args.gs_pdfsettings)
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

