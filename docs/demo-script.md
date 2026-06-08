# 2-Minute Demo Script

1. "This is my IT Operations RAG Knowledge Assistant. It uses fake SOPs, outage notes, ticket logs, asset inventory notes, and policy docs."
2. "First I build the Chroma index. The app loads TXT, CSV, and PDF files, splits them into chunks, creates embeddings, and stores the chunks with source metadata."
3. "Now I ask a question: What is the escalation process for a P1 outage?"
4. "Without an API key, the app still works in retrieval-only mode and shows the most relevant source chunks."
5. "The important part is source transparency. I can expand the source chunks and verify exactly where the answer came from."
6. "If I add an OpenAI or OpenRouter API key, the app uses the retrieved chunks as context to generate a grounded answer."
7. "For safety, this repo uses fake data only and excludes `.env`, uploaded private docs, and the local Chroma database from GitHub."
