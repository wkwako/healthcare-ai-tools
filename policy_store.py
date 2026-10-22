import json
import re
from pathlib import Path
import chromadb

clean_path = Path(__file__).parent / "data" / "lcd" / "clean"
chroma_path = Path(__file__).parent / "data" / "chroma"
collection_name = "lcd_chunks"

#the default embedding model (all-MiniLM-L6-v2) ignores text past 256 tokens, roughly 1000 characters
MAX_CHUNK_CHARS = 800
#sections shorter than this are merged into the next one instead of becoming their own chunk
MIN_CHUNK_CHARS = 300

def split_long_line(line, max_chars=MAX_CHUNK_CHARS):
    """Splits a line longer than max_chars at sentence boundaries"""
    if len(line) <= max_chars:
        return [line]
    pieces, current = [], ""
    for sentence in re.split(r"(?<=[.;])\s+", line):
        if current and len(current) + len(sentence) + 1 > max_chars:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
    pieces.append(current)
    return pieces

def chunk_section(text, max_chars=MAX_CHUNK_CHARS, min_chars=MIN_CHUNK_CHARS):
    """Splits cleaned text into (heading, body) chunks along its ## headings"""
    lines = [piece for line in text.splitlines() for piece in split_long_line(line, max_chars)]
    chunks = []
    current_heading, chunk_heading = "", ""
    chunk_lines, size = [], 0
    for line in lines:
        heading_line = line.startswith("## ")
        if chunk_lines and ((heading_line and size >= min_chars) or size + len(line) > max_chars):
            chunks.append((chunk_heading, "\n".join(chunk_lines)))
            chunk_lines, size = [], 0
        if heading_line:
            current_heading = line[3:]
        if not chunk_lines:
            chunk_heading = current_heading
        chunk_lines.append(line)
        size += len(line) + 1
    if chunk_lines:
        chunks.append((chunk_heading, "\n".join(chunk_lines)))
    return chunks

def chunk_policy(policy):
    """Turns one cleaned LCD into chunks with ids and metadata for Chroma"""
    lcd_id = policy["lcd_id"]
    chunks = []
    for section, text in policy["sections"].items():
        for n, (heading, body) in enumerate(chunk_section(text)):
            #a chunk split off mid-section repeats its heading so it keeps its context
            header = f"{policy['title']} (L{lcd_id})"
            if heading and not body.startswith("## "):
                header += f"\n## {heading}"
            chunks.append({
                "id": f"L{lcd_id}-{section}-{n}",
                "text": f"{header}\n{body}",
                "metadata": {
                    "lcd_id": lcd_id,
                    "title": policy["title"],
                    "version": policy["version"],
                    "section": section,
                    "heading": heading,
                    #Chroma metadata values must be single strings or numbers
                    "contractors": "; ".join(policy["contractors"]),
                },
            })
    return chunks

def get_collection():
    client = chromadb.PersistentClient(path=str(chroma_path))
    return client.get_or_create_collection(collection_name)

def build_vector_store():
    """Rebuilds the collection from scratch from the cleaned LCD files"""
    client = chromadb.PersistentClient(path=str(chroma_path))
    if collection_name in [c.name for c in client.list_collections()]:
        client.delete_collection(collection_name)
    collection = client.create_collection(collection_name)

    chunks = []
    for file in sorted(clean_path.glob("*.json")):
        chunks.extend(chunk_policy(json.loads(file.read_text(encoding="utf-8"))))

    collection.add(
        ids=[chunk["id"] for chunk in chunks],
        documents=[chunk["text"] for chunk in chunks],
        metadatas=[chunk["metadata"] for chunk in chunks],
    )
    return len(chunks)

def query_policies(query, n_results=5):
    """Returns the closest chunks to a query as a list of dicts, best match first"""
    results = get_collection().query(query_texts=[query], n_results=n_results)
    return [
        {"id": id, "distance": distance, "text": text, **metadata}
        for id, distance, text, metadata in zip(
            results["ids"][0], results["distances"][0],
            results["documents"][0], results["metadatas"][0])
    ]

if __name__ == "__main__":
    print(f"Stored {build_vector_store()} chunks")

    #sanity check: the PAP policy (L33718) should rank above the distractors
    for query in ["CPAP coverage criteria", "bi-level device after CPAP failed",
                  "hypoglossal nerve stimulation BMI requirement", "home oxygen with PAP therapy"]:
        print(f"\n{query}")
        for result in query_policies(query):
            print(f"  {result['distance']:.3f}  L{result['lcd_id']}  {result['title'][:45]}  | {result['heading'][:40]}")
