import shutil

import streamlit as st

from rag_pipeline import (
    SAMPLE_DIR,
    UPLOAD_DIR,
    build_vector_store,
    get_llm_answer,
    load_documents_from_folder,
    load_vector_store,
)


st.set_page_config(
    page_title="IT Ops RAG Knowledge Assistant",
    page_icon="🔎",
    layout="wide",
)

st.title("IT Operations RAG Knowledge Assistant")
st.caption(
    "Upload sample SOPs, outage notes, ticket logs, asset notes, or policy docs. "
    "Ask questions and inspect the exact source chunks used."
)


with st.sidebar:
    st.header("Build Knowledge Base")
    st.write("Use the sample docs first. Only upload non-sensitive IT Operations practice files.")

    uploaded_files = st.file_uploader(
        "Upload TXT, CSV, or PDF files",
        type=["txt", "csv", "pdf"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        for file in uploaded_files:
            target = UPLOAD_DIR / file.name
            target.write_bytes(file.getbuffer())
        st.success(f"Saved {len(uploaded_files)} uploaded file(s).")

    source_choice = st.radio(
        "Document source",
        ["Sample docs only", "Uploaded docs only", "Sample + uploaded docs"],
    )

    if st.button("Build / Rebuild Chroma Index", type="primary"):
        folders = []
        if source_choice in ["Sample docs only", "Sample + uploaded docs"]:
            folders.append(SAMPLE_DIR)
        if source_choice in ["Uploaded docs only", "Sample + uploaded docs"]:
            folders.append(UPLOAD_DIR)

        docs = []
        for folder in folders:
            docs.extend(load_documents_from_folder(folder))

        if not docs:
            st.error("No documents found. Use the sample docs or upload files first.")
        else:
            with st.spinner("Building embeddings and saving chunks to Chroma..."):
                vector_store, chunks, chroma_dir = build_vector_store(docs)
            st.session_state["vector_store"] = vector_store
            st.session_state["chroma_dir"] = str(chroma_dir)
            st.session_state["index_ready"] = True
            st.success(f"Indexed {len(docs)} document sections into {len(chunks)} chunks.")

    if st.button("Clear Uploaded Docs"):
        if UPLOAD_DIR.exists():
            shutil.rmtree(UPLOAD_DIR)
        UPLOAD_DIR.mkdir(exist_ok=True)
        st.success("Uploaded docs cleared.")


question = st.text_input(
    "Ask an IT Operations question",
    placeholder="Example: What is the escalation process for a P1 outage?",
)

top_k = st.slider("Number of source chunks to retrieve", min_value=2, max_value=6, value=3)

if st.button("Ask", type="primary") and question:
    try:
        with st.spinner("Retrieving relevant source chunks..."):
            vector_store = st.session_state.get("vector_store")
            if vector_store is None:
                vector_store = load_vector_store(st.session_state.get("chroma_dir"))
            retrieved_docs = vector_store.similarity_search(question, k=top_k)

        if not retrieved_docs:
            st.warning("No relevant chunks found. Rebuild the index or add more documents.")
        else:
            answer = get_llm_answer(question, retrieved_docs)

            st.subheader("Answer")
            st.write(answer)

            st.subheader("Source Chunks Used")
            for i, doc in enumerate(retrieved_docs, start=1):
                meta = doc.metadata
                source_label = meta.get("source", "Unknown source")
                page_label = f", page {meta.get('page')}" if meta.get("page") else ""
                row_label = f", row {meta.get('row')}" if meta.get("row") is not None else ""

                with st.expander(
                    f"Source {i}: {source_label}{page_label}{row_label}",
                    expanded=True,
                ):
                    st.write(doc.page_content)
                    st.caption(f"Metadata: {meta}")

    except Exception as e:
        st.error(f"Something went wrong: {e}")
        st.info("Try clicking 'Build / Rebuild Chroma Index' in the sidebar first.")
