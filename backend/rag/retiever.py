import os
import re
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

API_KEY = os.getenv("GROQ_API_KEY")

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

from groq import Groq
from sentence_transformers import CrossEncoder

# Setup paths
DATA_DIR = BASE_DIR / "data"
INDEX_DIR = DATA_DIR / "faiss_index"

_db = None
_embeddings = None
_reranker = None

def get_vector_db():
    """Lazy initialize and return the FAISS vector database."""
    global _db, _embeddings
    if _db is None:
        if not INDEX_DIR.exists():
            raise FileNotFoundError(
                f"FAISS index directory not found at {INDEX_DIR}. "
                "Please run 'python backend/rag/ingest.py' first to build the index."
            )
        
        _embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        
        # Load FAISS index locally
        _db = FAISS.load_local(
            str(INDEX_DIR), 
            _embeddings, 
            allow_dangerous_deserialization=True
        )
    return _db

def get_reranker():
    """Lazy initialize and return the CrossEncoder reranking model."""
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=512)
    return _reranker

def detect_module_from_docs(docs) -> str:
    """Detect module based on retrieved document metadata."""
    modules = [doc.metadata.get("module") for doc in docs if doc.metadata.get("module")]
    if not modules:
        return None
        
    # Count occurrences
    from collections import Counter
    most_common = Counter(modules).most_common(1)[0][0]
    
    # Map to frontend modules: "MM" | "SD" | "S4"
    if "SD" in most_common:
        return "SD"
    elif "MM" in most_common:
        return "MM"
    elif "S/4HANA" in most_common or "S4" in most_common:
        return "S4"
    return None

def run_rag(message: str, history: list) -> dict:
    """
    Main RAG pipeline:
      1. Retrieve raw candidate documents locally (FAISS dense search + exact keyword search).
      2. Re-rank the merged candidates using local Cross-Encoder to select the top 5.
      3. Construct a strict system prompt with re-ranked context.
      4. Call Groq's API directly using the native SDK (Llama-3.1-8b-instant).
      5. Extract module tags and unique source page citations.
    """
    db = None
    dense_docs = []
    try:
        db = get_vector_db()
        dense_docs = db.similarity_search(message, k=12)
    except Exception as e:
        print(f"[RAG ERROR] Vector database retrieval failed: {e}")

    keyword_docs = []
    if db:
        try:
            acronyms = re.findall(r'\b[A-Z0-9_/]{3,20}\b', message)
            all_words = re.findall(r'\b\w{3,20}\b', message)
            
            stop_words = {
                "WHAT", "HOW", "WHY", "THE", "AND", "FOR", "SAP", "OUT", "ARE", 
                "THEY", "THAT", "THIS", "WITH", "THIS", "HERE", "SOME", "MORE", "INFO"
            }
            
            search_terms = [t for t in (acronyms if acronyms else all_words) if t.upper() not in stop_words]
            
            if search_terms:
                docstore = db.docstore._dict.values()
                for doc in docstore:
                    content = doc.page_content.upper()
                    if any(re.search(r'\b' + re.escape(term.upper()) + r'\b', content) for term in search_terms):
                        keyword_docs.append(doc)
        except Exception as e:
            print(f"[RAG ERROR] Keyword search failed: {e}")

    candidate_map = {}
    for doc in keyword_docs[:15]:
        candidate_map[doc.page_content] = doc
    for doc in dense_docs:
        if doc.page_content not in candidate_map:
            candidate_map[doc.page_content] = doc
            
    candidates = list(candidate_map.values())

    if not candidates:
        return {
            "text": "I am sorry, but I cannot find this information in the provided resources.",
            "module": None,
            "sources": []
        }

    try:
        reranker = get_reranker()
        pairs = [[message, doc.page_content] for doc in candidates]
        scores = reranker.predict(pairs)
        
        scored_docs = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
        
        top_scored_docs = scored_docs[:5]
        top_docs = [doc for score, doc in top_scored_docs]
        top_scores = [score for score, doc in top_scored_docs]
        
        print(f"[Rerank Logger] Top score: {top_scores[0]:.4f} | Lowest selected: {top_scores[-1]:.4f}")
        
        if top_scores[0] < -9.5:
            print(f"[Rerank Logger] Top candidate score ({top_scores[0]:.4f}) falls below threshold (-9.5). Rejecting.")
            return {
                "text": "I am sorry, but I cannot find this information in the provided resources.",
                "module": None,
                "sources": []
            }
            
    except Exception as e:
        print(f"[RAG ERROR] Re-ranking failed: {e}. Falling back to default top-5 vectors.")
        top_docs = candidates[:5]

    context_chunks = []
    sources = []
    
    for doc in top_docs:
        context_chunks.append(doc.page_content)
        source_name = doc.metadata.get("source", "Unknown PDF")
        page_num = doc.metadata.get("page", 1)
        sources.append(f"{source_name} (Page {page_num})")
        
    context_text = "\n\n---\n\n".join(context_chunks)
    
    unique_sources = []
    for src in sources:
        if src not in unique_sources:
            unique_sources.append(src)

    detected_module = detect_module_from_docs(top_docs)

    system_prompt = (
        "You are an expert SAP Consultant Chatbot specializing in SAP Materials Management (MM) "
        "and SAP Sales and Distribution (SD) modules.\n\n"
        "CRITICAL RULE: You must answer the user's question ONLY using the provided retrieved context. "
        "Do not invent facts, do not make up details, and do not use any outside knowledge not present in the context.\n\n"
        "Handling Brief Context / Lists:\n"
        "If the retrieved context contains the requested BAPI, table, transaction, or concept (even if it is just a brief entry in a list with technical fields like 'Description', 'Method', 'Business Object', 'Interface Type', etc.), "
        "you MUST present those details clearly to the user as your answer. Do not say you cannot find it if it is listed in the context.\n"
        "Only respond with exactly 'I am sorry, but I cannot find this information in the provided resources.' if the requested item is completely missing or not mentioned in the retrieved context.\n\n"
        "Citations Requirement:\n"
        "For every claim or explanation you make, you MUST cite the source document name and page number exactly as shown "
        "in the 'Document:' and 'Page:' lines preceding the information in the context block.\n"
        "Format inline citations as: `[filename.pdf, Page: X]` (e.g. `[SAP SD VBAK-VBAP.pdf, Page: 2]`).\n"
        "Do not invent document names or page numbers that are not explicitly shown in the context below.\n\n"
        "But if some query not about SAP or it is about any country and outside question don't answer it. Say i'm a sap bot, can answer about SAP.\n"
        "But reply about greetings such as hello , hi"
        f"--- RETRIEVED CONTEXT ---\n{context_text}\n-------------------------"
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
            
    # Add the current user query
    messages.append({"role": "user", "content": message})

    if not API_KEY:
        answer = "[ERROR] GROQ_API_KEY is not set in .env. Please add it to start chatting."
    else:
        try:
            client = Groq(api_key=API_KEY)
            completion = client.chat.completions.create(
                messages=messages,
                model="llama-3.1-8b-instant",
                temperature=0.1  # low temperature for strict grounding
            )
            answer = completion.choices[0].message.content
        except Exception as e:
            answer = f"[ERROR] Failed to get response from Groq: {e}"

    return {
        "text": answer,
        "module": detected_module,
        "sources": unique_sources
    }