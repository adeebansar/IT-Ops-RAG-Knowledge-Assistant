import os
import shutil
import hashlib
import math
from pathlib import Path
from typing import List

import pandas as pd
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except Exception:
    HuggingFaceEmbeddings = None

try:
    from langchain_openai import ChatOpenAI
except Exception:
    ChatOpenAI = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


load_dotenv()

APP_DIR = Path(__file__).parent
UPLOAD_DIR = APP_DIR / "uploaded_docs"
SAMPLE_DIR = APP_DIR / "sample_docs"
CHROMA_DIR = APP_DIR / "chroma_db"
COLLECTION_NAME = "itops_knowledge"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
USE_HUGGINGFACE_EMBEDDINGS = os.getenv("USE_HUGGINGFACE_EMBEDDINGS", "").lower() in {
    "1",
    "true",
    "yes",
}

UPLOAD_DIR.mkdir(exist_ok=True)
SAMPLE_DIR.mkdir(exist_ok=True)


class LocalHashEmbeddings(Embeddings):
    """Small offline fallback so the beginner demo still works without model downloads."""

    def __init__(self, size: int = 384):
        self.size = size

    def _embed(self, text: str) -> List[float]:
        vector = [0.0] * self.size
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.size
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        length = math.sqrt(sum(value * value for value in vector))
        if not length:
            return vector
        return [value / length for value in vector]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._embed(text)


def get_embeddings():
    if not USE_HUGGINGFACE_EMBEDDINGS:
        return LocalHashEmbeddings()

    try:
        if HuggingFaceEmbeddings is None:
            raise RuntimeError("langchain-huggingface is not installed")
        return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    except Exception:
        return LocalHashEmbeddings()


def load_txt(path: Path) -> List[Document]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [Document(page_content=text, metadata={"source": path.name, "type": "txt"})]


def load_csv(path: Path) -> List[Document]:
    df = pd.read_csv(path)
    docs = []
    for idx, row in df.iterrows():
        row_text = "\n".join([f"{col}: {row[col]}" for col in df.columns])
        docs.append(
            Document(
                page_content=row_text,
                metadata={"source": path.name, "row": int(idx), "type": "csv"},
            )
        )
    return docs


def load_pdf(path: Path) -> List[Document]:
    if PdfReader is None:
        raise RuntimeError("pypdf is not installed. Run: pip install pypdf")

    reader = PdfReader(str(path))
    docs = []
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            docs.append(
                Document(
                    page_content=text,
                    metadata={"source": path.name, "page": page_num, "type": "pdf"},
                )
            )
    return docs


def load_documents_from_folder(folder: Path) -> List[Document]:
    all_docs = []
    for path in sorted(folder.glob("*")):
        if path.suffix.lower() == ".txt":
            all_docs.extend(load_txt(path))
        elif path.suffix.lower() == ".csv":
            all_docs.extend(load_csv(path))
        elif path.suffix.lower() == ".pdf":
            all_docs.extend(load_pdf(path))
    return all_docs


def split_documents(documents: List[Document]) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=650,
        chunk_overlap=120,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    return splitter.split_documents(documents)


def build_vector_store(documents: List[Document]):
    chunks = split_documents(documents)
    embeddings = get_embeddings()

    if CHROMA_DIR.exists():
        shutil.rmtree(CHROMA_DIR)
    CHROMA_DIR.mkdir(exist_ok=True)

    vector_store = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(CHROMA_DIR),
        collection_name=COLLECTION_NAME,
    )
    return vector_store, chunks


def load_vector_store():
    embeddings = get_embeddings()
    return Chroma(
        persist_directory=str(CHROMA_DIR),
        embedding_function=embeddings,
        collection_name=COLLECTION_NAME,
    )


def get_llm_answer(question: str, context_docs: List[Document]) -> str:
    context = "\n\n--- SOURCE CHUNK ---\n\n".join(
        [doc.page_content for doc in context_docs]
    )

    prompt = f"""
You are an IT Operations Knowledge Assistant.
Answer using only the provided source chunks.
If the answer is not in the source chunks, say: "I do not have enough information in the uploaded documents."
Keep the answer practical and concise.

Question:
{question}

Source chunks:
{context}
"""

    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if ChatOpenAI and openrouter_key:
        llm = ChatOpenAI(
            model="openai/gpt-4o-mini",
            api_key=openrouter_key,
            base_url="https://openrouter.ai/api/v1",
            temperature=0,
        )
        return llm.invoke(prompt).content

    if ChatOpenAI and openai_key:
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=openai_key,
            temperature=0,
        )
        return llm.invoke(prompt).content

    return (
        "No LLM API key found, so this is retrieval-only mode.\n\n"
        "Use the source chunks below as the grounded answer context.\n\n"
        "To enable generated answers, add OPENROUTER_API_KEY or OPENAI_API_KEY to your .env file."
    )
