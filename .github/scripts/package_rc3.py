#!/usr/bin/env python3
"""Build deterministic manual Home Assistant integration zip from frozen RC3 tree.

No release can contain private Mittelhof secrets or user booking data.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo

if len(sys.argv) != 3:
    raise SystemExit("Usage: package_rc3.py <frozen-source-dir> <dist-dir>")
root = Path(sys.argv[1]).resolve()
dest = Path(sys.argv[2]).resolve()
dest.mkdir(parents=True, exist_ok=True)
version = "0.7.0rc3"
folder = root / "custom_components" / "smoobu_mittelhof"
manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
if manifest.get("version") != version or manifest.get("domain") != "smoobu_mittelhof":
    raise SystemExit("FROZEN MANIFEST MISMATCH - refusing release")
files = sorted(
    (p for p in folder.rglob("*")
     if p.is_file() and not p.is_symlink()
     and "__pycache__" not in p.parts
     and p.suffix not in (".pyc", ".pyo")),
    key=lambda p: p.relative_to(root).as_posix(),
)
required = {
    "custom_components/smoobu_mittelhof/__init__.py",
    "custom_components/smoobu_mittelhof/manifest.json",
    "custom_components/smoobu_mittelhof/guest_finance.py",
    "custom_components/smoobu_mittelhof/invoice_portal.py",
    "custom_components/smoobu_mittelhof/frontend/mittelhof-guest-card.js",
}
included = {p.relative_to(root).as_posix() for p in files}
if len(files) < 20 or not required.issubset(included):
    raise SystemExit("Integration files missing - refusing incomplete release")
name = f"smoobu-mittelhof-{version}.zip"
archive = dest / name
with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=9) as z:
    for p in files:
        info = ZipInfo(p.relative_to(root).as_posix(), date_time=(2026, 11, 7, 0, 0, 0))
        info.compress_type = ZIP_DEFLATED
        info.external_attr = (0o644 & 0xFFFF) << 16
        z.writestr(info, p.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)
with ZipFile(archive) as z:
    if z.testzip() is not None or not required.issubset(set(z.namelist())):
        raise SystemExit("Release zip corrupt")
digest = sha256(archive.read_bytes()).hexdigest()
(dest / "SHA256SUMS.txt").write_text(f"{digest}  {name}\n", "utf-8")
print(f"{name}: {len(files)} integration files, sha256={digest}")
