import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
TEXT_DIR = DATA_DIR / "text files"

def detect_module(filename: str) -> str:
    """Detect SAP module from filename."""
    name_lower = filename.lower()
    for keywords, module in MODULE_RULES:
        if any(kw in name_lower for kw in keywords):
            return module
    return "SAP General"


def detect_source_pdf(filename: str) -> str:
    """Derive the source PDF name from the text filename."""
    stem = Path(filename).stem
    pdf_path = DATA_DIR / f"{stem}.pdf"
    if pdf_path.exists():
        return pdf_path.name
    return filename

def strip_trailing_footer_titles(text: str) -> str:
    """Remove repeated short product/section footer titles from end of page."""
    lines = text.rstrip().split('\n')
    while lines:
        last = lines[-1].strip()
        if not last:
            lines.pop()
            continue
        matched = False
        for pat in FOOTER_TITLE_PATTERNS:
            if pat.fullmatch(last):
                lines.pop()
                matched = True
                break
        if not matched:
            break
    return '\n'.join(lines)


def format_file(filepath: Path, dry_run: bool = False) -> bool:
    """Clean and format a single text file for RAG retrieval."""
    filename = filepath.name
    source_pdf = detect_source_pdf(filename)
    module = detect_module(filename)
    title = filepath.stem

    print(f"[*] Processing: {filename}")
    print(f"    Source: {source_pdf} | Module: {module}")

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"    [ERROR] Failed to read: {e}")
        return False
    content = re.sub(r'^---\n.*?\n---\n*', '', content, count=1, flags=re.DOTALL)

    # Split into pages
    pages = split_into_pages(content)

    if not pages:
        pages = [content]

    cleaned_pages = []
    for i, page in enumerate(pages, 1):
        cleaned = clean_page(page)
        if cleaned:
            header = f"# [Source: {source_pdf} | Page: {i} | Module: {module}]"
            cleaned_pages.append(f"{header}\n\n{cleaned}")

    if not cleaned_pages:
        print(f"    [WARNING] No content remained after cleaning")
        return False

    yaml_header = f"""---
source: {source_pdf}
module: {module}
title: {title}
---"""

    # Combine everything
    final_content = yaml_header + "\n\n" + "\n\n---\n\n".join(cleaned_pages) + "\n"

    if dry_run:
        return True

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(final_content)
        print(f"    [+] Saved: {len(cleaned_pages)} pages, {len(final_content)} chars")
        return True
    except Exception as e:
        print(f"    [ERROR] Failed to write: {e}")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Clean & format text files for RAG retrieval")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    if not TEXT_DIR.exists():
        print(f"[ERROR] Text directory not found: {TEXT_DIR}")
        return

    txt_files = sorted(TEXT_DIR.glob("*.txt"))
    if not txt_files:
        return

    success = 0
    for txt_file in txt_files:
        if format_file(txt_file, dry_run=args.dry_run):
            success += 1


if __name__ == "__main__":
    main()