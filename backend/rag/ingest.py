import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
TEXT_DIR = DATA_DIR / "text files"
INDEX_DIR = DATA_DIR / "faiss_index"

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
    except ImportError:
        from langchain.embeddings import HuggingFaceEmbeddings

try:
    from langchain_community.vectorstores import FAISS
except ImportError:
    from langchain_core.vectorstores import FAISS

from langchain_core.documents import Document

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
    except ImportError:
        class RecursiveCharacterTextSplitter:
            def __init__(self, chunk_size=1500, chunk_overlap=150):
                self.chunk_size = chunk_size
                self.chunk_overlap = chunk_overlap
            def split_text(self, text):
                words = text.split()
                chunks = []
                current_chunk = []
                current_len = 0
                for word in words:
                    current_chunk.append(word)
                    current_len += len(word) + 1
                    if current_len >= self.chunk_size:
                        chunks.append(" ".join(current_chunk))
                        current_chunk = current_chunk[-max(1, int(self.chunk_overlap/10)):]
                        current_len = sum(len(w)+1 for w in current_chunk)
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                return chunks

PAGE_HEADER_PATTERN = re.compile(r'^#\s*\[Source:\s*(.*?)\s*\|\s*Page:\s*(\d+)\s*\|\s*Module:\s*(.*?)\s*\]')

def parse_txt_file(filepath: Path) -> list[Document]:
    """
    Parses a formatted txt file, splitting it by page, and then using 
    RecursiveCharacterTextSplitter to split page contents into robust chunks under 1500 characters.
    """
    documents = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    content = re.sub(r'^---\n.*?\n---\n*', '', content, count=1, flags=re.DOTALL)
    
    pages = content.split('\n\n---\n\n')
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=150
    )
    
    for page in pages:
        page = page.strip()
        if not page:
            continue
            
        lines = page.split('\n')
        first_line = lines[0].strip()
        
        match = PAGE_HEADER_PATTERN.match(first_line)
        if match:
            source = match.group(1)
            page_num = match.group(2)
            module = match.group(3)
            page_text = '\n'.join(lines[1:]).strip()
        else:
            source = filepath.name
            page_num = "1"
            module = "SAP General"
            page_text = page
            
        if not page_text:
            continue
            
        chunks = text_splitter.split_text(page_text)
        
        for chunk in chunks:
            chunk = chunk.strip()
            if len(chunk) < 15:
                continue
                
            chunk_content = f"Document: {source}\nPage: {page_num}\nModule: {module}\nInformation:\n{chunk}"
            
            doc = Document(
                page_content=chunk_content,
                metadata={
                    "source": source,
                    "page": int(page_num),
                    "module": module
                }
            )
            documents.append(doc)
            
    return documents

def main():
    print("=" * 60)
    print("Starting Vector DB Ingestion (FAISS + HuggingFace + Recursive Splitter)")
    print(f"Reading from: {TEXT_DIR}")
    print("=" * 60)
    
    txt_files = list(TEXT_DIR.glob("*.txt"))
    if not txt_files:
        print(f"[ERROR] No text files found in {TEXT_DIR}")
        return
        
    all_docs = []
    for txt_file in txt_files:
        print(f"[*] Parsing: {txt_file.name}")
        docs = parse_txt_file(txt_file)
        all_docs.extend(docs)
        
    print(f"\nSuccessfully parsed {len(txt_files)} files into {len(all_docs)} recursive chunks.")
    
    print("\n[*] Initializing local HuggingFace Embeddings (all-MiniLM-L6-v2)...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    
    print("[*] Creating local FAISS Index (this will compute embeddings locally on your CPU)...")
    try:
        db = FAISS.from_documents(all_docs, embeddings)
        
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        db.save_local(str(INDEX_DIR))
        print(f"\n[+] FAISS Index successfully saved locally at: {INDEX_DIR}")
    except Exception as e:
        print(f"\n[ERROR] Failed to build vector DB: {e}")

if __name__ == "__main__":
    main()
