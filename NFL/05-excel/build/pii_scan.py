#!/usr/bin/env python3
"""Personal-data scan of an .xlsx package before it is published (this repository is public).

Usage:
    python3 pii_scan.py WORKBOOK.xlsx [--forbid WORD ...] [--forbid-file PATH] [--json]

Every part of the package is searched, including the inside of the Power Query package (DataMashup:
Section1.m, metadata, permissions) and the readable strings of binary parts such as the Data Model
(xl/model/item.data). Findings make the exit status 1.

Generic rules (no personal data is written in this file, which is public):
  * parts that carry people or machine data must be absent: comments, threaded comments, persons,
    revisions, printer settings, custom properties, external links, VBA;
  * docProps/core.xml dc:creator and cp:lastModifiedBy must be one of ALLOWED_AUTHORS;
    docProps/app.xml Company and Manager must be empty or absent;
  * xl/workbook.xml must not carry x15ac:absPath (the folder the file was last saved in) or fileSharing userName;
  * no Windows user folder (C:\\Users\\<name>, also in \\\\?\\ long-path form and 8.3 short form) unless <name> is a
    neutral placeholder (U000..., you, USER), no /Users/<name> or /home/<name>, no UNC path, no file:/// address,
    no e-mail address, no OneDrive or SharePoint web address;
  * a Data Model object path "<machine>\\LocalCube..." must name a neutral placeholder machine (PC000...).
The Data Model (xl/model/item.data, an Analysis Services backup) is read file by file: each inner file is
decompressed (MS-XCA plain LZ77) and its readable strings are scanned too.
With --candid (used for the experimental workbook, whose 1.x snapshot sheets were cleaned): references to the
owner's private 1.x source transcript and the critical remark about a third-party project must not reappear.
Words to forbid in addition (for example the owner's name, which must not be written here) come from --forbid,
--forbid-file (one word per line; keep that file outside the repository or in a git-ignored folder) and the
environment variable PII_FORBID (comma-separated). They are matched case-insensitively in UTF-8, UTF-16 and
plain-ASCII forms anywhere in the package.
"""
import argparse
import base64
import io
import json
import os
import re
import struct
import sys
import zipfile
import zlib

ALLOWED_AUTHORS = {"", "NFL-Analysis Committee (Claude)", "NFL-Analysis build_workbook.py",
                   "NFL-Analysis build_queries_installed.py", "wes-blue"}
NEUTRAL_USER = re.compile(r"^(U0+|you|USER)$", re.I)
NEUTRAL_MACHINE = re.compile(r"^PC0+$")
FORBIDDEN_PARTS = [
    (r"^xl/comments\d*\.xml$", "cell comments (carry the author's name)"),
    (r"^xl/threadedComments/", "threaded comments (carry the author's name)"),
    (r"^xl/persons/", "persons list (user names of commenters)"),
    (r"^xl/revisions/", "shared-workbook revision log (user names)"),
    (r"^xl/printerSettings/", "printer settings (printer and machine names)"),
    (r"^docProps/custom\.xml$", "custom document properties"),
    (r"^xl/externalLinks/", "external workbook links (local paths)"),
    (r"^xl/vbaProject\.bin$", "VBA project"),
    (r"^xl/drawings/vmlDrawing", "legacy comment drawings"),
]
PATTERNS = [
    ("windows user folder", re.compile(r"(?i)[A-Z]:\\(?:Users|Documents and Settings)\\([^\\/\"<>|:*?\r\n]+)")),
    ("unix user folder", re.compile(r"(?:/Users/|/home/)([A-Za-z0-9._-]+)")),
    ("UNC path", re.compile(r"(?<![\\\"])\\\\(?!\?\\)[A-Za-z0-9_.$-]+\\[A-Za-z0-9_.$-]+")),
    ("file address", re.compile(r"(?i)file:///[^\s\"<]*")),
    ("e-mail address", re.compile(r"[A-Za-z0-9._%+-]{2,}@[A-Za-z0-9-]{2,}(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")),
    ("OneDrive/SharePoint address", re.compile(r"(?i)https?://[^\s\"<]*(?:sharepoint\.com|docs\.live\.net|onedrive\.live\.com|1drv\.ms)[^\s\"<]*")),
    ("8.3 short user name in a path", re.compile(r"(?i)\\Users\\([A-Z0-9_]{1,6}~\d)\\")),
    ("Data Model machine name", re.compile(r"<ObjectPath>([^\\<]+)\\LocalCube")),
]
# Candid or private-source text (QA-m10). Generic wording only: nothing personal is written here.
CANDID_PATTERNS = [
    ("reference to the private 1.x source transcript", re.compile(r"(?i)\btranscript\b")),
    ("critical remark about a third-party project", re.compile(r"(?i)\bmaps an outdated column name\b|\bneeds R and\b")),
]


# ---------------------------------------------------------------- Data Model (Analysis Services backup, "ABF")
_REV8 = bytes(int("{:08b}".format(i)[::-1], 2) for i in range(256))


def crc32_bzip2(b):
    """CRC-32/BZIP2 (polynomial 0x04C11DB7, not reflected, init and xorout 0xFFFFFFFF): the 4-byte trailer that the
    Data Model stores, little-endian, after every inner file. Computed through zlib's reflected CRC-32 on bit-reversed
    bytes."""
    c = zlib.crc32(b.translate(_REV8))
    return int("{:032b}".format(c)[::-1], 2)


def abf_files(b):
    """Inner files of a Data Model part: list of (name, offset, stored size incl. the 4-byte CRC trailer).
    Layout: signature, a UTF-16 BackupLog header in the first 4096 bytes giving the offset of the VirtualDirectory
    (m_cbOffsetHeader), and the VirtualDirectory listing each file's Path, Size and m_cbOffsetHeader."""
    head = b[:4096].decode("utf-16-le", "ignore")
    m = re.search(r"<m_cbOffsetHeader>(\d+)</m_cbOffsetHeader>", head)
    if not m or "STREAM_STORAGE_SIGNATURE" not in head:
        raise ValueError("not an Analysis Services backup")
    vd = b[int(m.group(1)):].decode("utf-16-le", "ignore")
    return [(f.group(1), int(f.group(3)), int(f.group(2))) for f in re.finditer(
        r"<BackupFile><Path>([^<]*)</Path><Size>(\d+)</Size><m_cbOffsetHeader>(\d+)</m_cbOffsetHeader>", vd)]


def _lz77(src, limit):
    """MS-XCA plain LZ77 decompression."""
    out, i, flags, cnt, last, n = bytearray(), 0, 0, 0, 0, len(src)
    while len(out) < limit:
        if cnt == 0:
            if i + 4 > n:
                break
            flags, i, cnt = struct.unpack_from("<I", src, i)[0], i + 4, 32
        cnt -= 1
        if not (flags >> cnt) & 1:
            if i >= n:
                break
            out.append(src[i])
            i += 1
            continue
        if i + 2 > n:
            break
        mb = struct.unpack_from("<H", src, i)[0]
        i += 2
        ml, mo = mb % 8, mb // 8 + 1
        if ml == 7:
            if last == 0:
                ml, last, i = src[i] % 16, i, i + 1
            else:
                ml, last = src[last] // 16, 0
            if ml == 15:
                ml, i = src[i], i + 1
                if ml == 255:
                    ml, i = struct.unpack_from("<H", src, i)[0], i + 2
                    if ml == 0:
                        ml, i = struct.unpack_from("<I", src, i)[0], i + 4
                    ml -= 22
                ml += 15
            ml += 7
        ml += 3
        for _ in range(ml):
            out.append(out[-mo])
    return bytes(out[:limit])


def abf_inner(b, off, size):
    """Content of one inner file: chunks of (uint16 uncompressed size, uint16 stored size, data), stored raw when the
    sizes are equal, else LZ77; files that start with a UTF-16 byte-order mark (the logs) are stored as they are."""
    body = b[off:off + size - 4]
    if body[:2] == b"\xff\xfe":
        return body
    out, p = bytearray(), 0
    while p + 4 <= len(body):
        us, cs = struct.unpack_from("<HH", body, p)
        pay = body[p + 4:p + 4 + cs]
        p += 4 + cs
        out += pay if cs == us else _lz77(pay, us)
    if p != len(body):
        raise ValueError("chunk framing")
    return bytes(out)


def decode_text(b):
    """Text of a part, or None if it is binary (a UTF-16 part counts as text only if it is XML)."""
    if b[:2] == b"\xff\xfe":
        t = b[2:].decode("utf-16-le", "replace")
        return t if t.lstrip("\ufeff").startswith("<") and "\ufffd" not in t else None
    if b[:3] == b"\xef\xbb\xbf":
        b = b[3:]
    try:
        t = b.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if "\x00" in t[:4096]:
        return None
    return t


def binary_strings(b):
    """Readable runs (ASCII and UTF-16LE) of a binary part, joined by newlines."""
    a = [m.group().decode("ascii") for m in re.finditer(rb"[\x20-\x7e\t]{4,}", b)]
    u = [m.group().decode("utf-16-le") for m in re.finditer(rb"(?:[\x20-\x7e\t]\x00){4,}", b)]
    return "\n".join(a + u)


def mashup_texts(text, name):
    """The inside of a DataMashup customXml item: package parts, permissions, metadata."""
    m = re.search(r"<DataMashup[^>]*>([A-Za-z0-9+/=\s]+)</DataMashup>", text)
    if not m:
        return []
    blob = base64.b64decode(re.sub(r"\s", "", m.group(1)))
    out = []
    p = 4
    blocks = []
    for _ in range(4):
        if p + 4 > len(blob):
            break
        n = struct.unpack("<I", blob[p:p + 4])[0]
        blocks.append(blob[p + 4:p + 4 + n])
        p += 4 + n
    if len(blocks) != 4:
        return [(name + "!DataMashup", binary_strings(blob))]
    pkg, perm, meta, bind = blocks
    try:
        with zipfile.ZipFile(io.BytesIO(pkg)) as z:
            for i in z.infolist():
                t = decode_text(z.read(i.filename))
                out.append((name + "!package/" + i.filename, t if t is not None else binary_strings(z.read(i.filename))))
    except zipfile.BadZipFile:
        out.append((name + "!package", binary_strings(pkg)))
    out.append((name + "!permissions", decode_text(perm) or binary_strings(perm)))
    if len(meta) >= 8:
        ml = struct.unpack("<I", meta[4:8])[0]
        out.append((name + "!metadata", meta[8:8 + ml].decode("utf-8", "replace")))
        rest = meta[8 + ml:]
        if len(rest) > 4:
            cl = struct.unpack("<I", rest[:4])[0]
            content = rest[4:4 + cl]
            if content:
                try:
                    with zipfile.ZipFile(io.BytesIO(content)) as z:
                        for i in z.infolist():
                            out.append((name + "!metadata-content/" + i.filename, binary_strings(z.read(i.filename))
                                        if decode_text(z.read(i.filename)) is None else decode_text(z.read(i.filename))))
                except zipfile.BadZipFile:
                    out.append((name + "!metadata-content", binary_strings(content)))
    out.append((name + "!bindings", binary_strings(bind)))
    return out


def load_forbidden(args_forbid, forbid_file):
    words = list(args_forbid or [])
    if forbid_file:
        with open(forbid_file, encoding="utf-8") as f:
            words += [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    env = os.environ.get("PII_FORBID", "")
    words += [w.strip() for w in env.split(",") if w.strip()]
    return [w for w in words if len(w) >= 3]


def scan(path, forbid=(), candid=False):
    """Return (findings, inventory). A finding is a dict(part, rule, detail). candid=True adds CANDID_PATTERNS."""
    findings, inv = [], {"parts": 0, "model_inner_files": 0, "defined_names": [], "connections": [], "core": {}, "app": {},
                         "texts_scanned": 0, "binary_parts": []}
    with zipfile.ZipFile(path) as z:
        parts = [(i.filename, z.read(i.filename)) for i in z.infolist()]
    inv["parts"] = len(parts)

    def add(part, rule, detail):
        findings.append({"part": part, "rule": rule, "detail": detail[:300]})

    texts = []
    for name, b in parts:
        for pat, why in FORBIDDEN_PARTS:
            if re.search(pat, name):
                add(name, "part present", why)
        t = None if re.search(r"\.(data|bin)$", name) else decode_text(b)
        if t is None:
            inv["binary_parts"].append(name)
            texts.append((name + " (readable strings)", binary_strings(b)))
            if name.startswith("xl/model/"):
                try:
                    inner = abf_files(b)
                except ValueError:
                    inner = []
                for fname, off, size in inner:
                    try:
                        texts.append((name + "!" + fname, binary_strings(abf_inner(b, off, size))))
                    except (ValueError, IndexError, struct.error):
                        add(name, "Data Model inner file not readable", fname)
                inv["model_inner_files"] = len(inner)
            continue
        texts.append((name, t))
        if "<DataMashup" in t:
            texts.extend(mashup_texts(t, name))

    d = dict(parts)
    core = decode_text(d.get("docProps/core.xml", b"")) or ""
    for tag in ("dc:creator", "cp:lastModifiedBy", "dc:title", "cp:version", "cp:lastPrinted", "dc:description",
                "cp:keywords", "dc:subject", "cp:category", "cp:contentStatus"):
        m = re.search(r"<%s[^>]*>([^<]*)</%s>" % (tag, tag), core)
        if m:
            inv["core"][tag] = m.group(1)
    for tag in ("dc:creator", "cp:lastModifiedBy"):
        v = inv["core"].get(tag, "")
        if v not in ALLOWED_AUTHORS:
            add("docProps/core.xml", "author not allowed", "%s = %r (allowed: %s)" % (tag, v, sorted(ALLOWED_AUTHORS)))
    app = decode_text(d.get("docProps/app.xml", b"")) or ""
    for tag in ("Company", "Manager", "Application", "AppVersion"):
        m = re.search(r"<%s>([^<]*)</%s>" % (tag, tag), app)
        if m:
            inv["app"][tag] = m.group(1)
            if tag in ("Company", "Manager") and m.group(1).strip():
                add("docProps/app.xml", tag, m.group(1))
    wbx = decode_text(d.get("xl/workbook.xml", b"")) or ""
    m = re.search(r"absPath[^>]*url=\"([^\"]*)\"", wbx)
    if m:
        add("xl/workbook.xml", "x15ac:absPath (folder where the file was last saved)", m.group(1))
    m = re.search(r"<fileSharing[^>]*userName=\"([^\"]*)\"", wbx)
    if m:
        add("xl/workbook.xml", "fileSharing userName", m.group(1))
    inv["defined_names"] = re.findall(r"<definedName name=\"([^\"]+)\"[^>]*>([^<]*)</definedName>", wbx)
    for n, ref in inv["defined_names"]:
        if "[" in ref or ":\\" in ref:
            add("xl/workbook.xml", "defined name refers outside the workbook", "%s = %s" % (n, ref))
    conn = decode_text(d.get("xl/connections.xml", b"")) or ""
    for m in re.finditer(r"connection=\"([^\"]*)\"", conn):
        cs = m.group(1).replace("&quot;", '"')
        inv["connections"].append(cs)
        if "Data Source=$Workbook$" not in cs and cs != "Data Model Connection":
            add("xl/connections.xml", "connection to a source outside the workbook", cs)

    for name, t in texts:
        if not t:
            continue
        inv["texts_scanned"] += 1
        for rule, rx in PATTERNS + (CANDID_PATTERNS if candid else []):
            for m in rx.finditer(t):
                g = m.group(1) if m.groups() else m.group(0)
                if rule in ("windows user folder", "8.3 short user name in a path", "unix user folder"):
                    if NEUTRAL_USER.match(g.strip()):
                        continue
                if rule == "Data Model machine name" and NEUTRAL_MACHINE.match(g):
                    continue
                add(name, rule, m.group(0))
        low = t.lower()
        for w in forbid:
            if w.lower() in low:
                i = low.index(w.lower())
                add(name, "forbidden word", "%r near: %s" % (w, t[max(0, i - 40):i + 40].replace("\n", " ")))
    # forbidden words in raw bytes (any part, any of the three encodings), in case a decoder missed them
    for name, b in parts:
        lb = b.lower()
        for w in forbid:
            for enc in (w.lower().encode("utf-8"), w.lower().encode("utf-16-le")):
                if enc in lb and not any(f["part"].startswith(name) and f["rule"] == "forbidden word" for f in findings):
                    add(name, "forbidden word (raw bytes)", repr(w))
    # one finding per (part, rule, detail)
    seen, uniq = set(), []
    for f in findings:
        k = (f["part"], f["rule"], f["detail"])
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq, inv


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("workbook")
    ap.add_argument("--forbid", action="append", help="a word that must not appear (repeatable)")
    ap.add_argument("--forbid-file", help="file with one forbidden word per line (keep it out of the repository)")
    ap.add_argument("--candid", action="store_true", help="also fail on private-source references and candid remarks")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    words = load_forbidden(a.forbid, a.forbid_file)
    findings, inv = scan(a.workbook, words, candid=a.candid)
    if a.json:
        print(json.dumps({"findings": findings, "inventory": inv, "forbidden_words_checked": len(words)}, indent=1))
    else:
        print("parts: %d, texts scanned: %d, forbidden words checked: %d" % (inv["parts"], inv["texts_scanned"], len(words)))
        print("core.xml: %s" % inv["core"])
        print("app.xml: %s" % inv["app"])
        print("defined names: %d; connections: %d (all inside the workbook unless listed below)"
              % (len(inv["defined_names"]), len(inv["connections"])))
        print("binary parts (readable strings scanned): %s; Data Model inner files decompressed and scanned: %d"
              % (inv["binary_parts"], inv["model_inner_files"]))
        for f in findings:
            print("FINDING  %-45s %-40s %s" % (f["part"], f["rule"], f["detail"]))
        print("PERSONAL-DATA SCAN: %s" % ("CLEAN" if not findings else "%d FINDING(S)" % len(findings)))
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
