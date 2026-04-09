import os
import json
from urllib.parse import urlparse

from qdrant_client import QdrantClient
from llama_index.core import VectorStoreIndex, StorageContext, Document
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core import Settings

# --- CONFIGURATION ---
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "incidents")

_qdrant_url = os.getenv("QDRANT_URL", "")
if _qdrant_url:
    _parsed = urlparse(_qdrant_url)
    QDRANT_HOST = _parsed.hostname or "localhost"
    QDRANT_PORT = _parsed.port or 6333
else:
    QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))

def initialize_system():
    """Initialize LlamaIndex settings and Qdrant connection.
    
    Embeddings are configured via environment variables:
        EMBED_PROVIDER (google, openai, local, etc.)
        EMBED_MODEL (gemini-embedding-2-preview, etc.)
    
    IMPORTANT: Run this AFTER settings are configured, or import setup_defaults.
    """
    client = QdrantClient(url=f"http://{QDRANT_HOST}:{QDRANT_PORT}")

    # Force Reset (Delete and Create)
    if client.collection_exists(COLLECTION_NAME):
        print(f"Deleting existing collection: {COLLECTION_NAME}...")
        client.delete_collection(collection_name=COLLECTION_NAME)

    # Initialize LlamaIndex Qdrant Store
    # Note: LlamaIndex will create the collection automatically with the right dimensions
    # based on the currently configured embed_model in Settings
    vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION_NAME)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    
    embed_model_name = getattr(Settings.embed_model, 'model_name', 
                              getattr(Settings.embed_model, '__class__.__name__', 'unknown'))
    print(f"✅ LlamaIndex + Qdrant Initialized with embed_model={embed_model_name}")
    return storage_context

def seed_data(storage_context):
    file_path = os.path.join(os.path.dirname(__file__), "incidents.json")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            incident_data = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: The file {file_path} was not found.")
        return None
    except json.JSONDecodeError:
        print(f"❌ Error: Failed to decode JSON from {file_path}.")
        return None

    documents = []
    for item in incident_data:
        # LlamaIndex wraps data into Document objects
        doc = Document(
            text=item["description"],
            doc_id=item["id"],
            metadata={
                "incident_id": item["id"],
                "summary": item["description"],
                "resolution": item.get("resolution", ""),
                "timestamp": "2026-04-08T10:00:00Z"
            }
        )
        documents.append(doc)

    # This one line handles embedding AND upserting to Qdrant
    index = VectorStoreIndex.from_documents(
        documents, storage_context=storage_context
    )
    print(f"✅ Seeded {len(documents)} incidents into LlamaIndex.")
    return index

def verify_seeded_data(index, query_text="DNS failure"):
    print(f"\n🔎 Testing LlamaIndex Retrieval for: '{query_text}'")
    
    # Create a retriever from the index
    retriever = index.as_retriever(similarity_top_k=3)
    results = retriever.retrieve(query_text)

    if not results:
        print("❌ No results found.")
        return

    for i, res in enumerate(results):
        # res is a NodeWithScore object
        meta = res.node.metadata
        print(f"\nResult #{i+1} (Score: {res.score:.4f})")
        print(f"ID: {meta.get('incident_id')}")
        print(f"Summary: {meta.get('summary')}")
        print(f"Resolution: {meta.get('resolution')}")

if __name__ == "__main__":
    from src.utils.setup import setup_defaults
    from dotenv import load_dotenv

    load_dotenv()
    setup_defaults()

    storage_ctx = initialize_system()
    idx = seed_data(storage_ctx)
    verify_seeded_data(idx, "Cant login and my new password wont arrive into my email wtff")