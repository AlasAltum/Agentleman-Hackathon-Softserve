import os
import uuid
from qdrant_client import QdrantClient
from llama_index.core import VectorStoreIndex, StorageContext, Document
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.embeddings.fastembed import FastEmbedEmbedding
from llama_index.core import Settings
import json

# --- CONFIGURATION ---
COLLECTION_NAME = "incidents"
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))

def initialize_system():
    # 1. Setup global settings for LlamaIndex (using your local FastEmbed models)
    # CLIP works for both text and vision, but for standard RAG, 
    # we usually set the default text embedder.
    Settings.embed_model = FastEmbedEmbedding(model_name="BAAI/bge-small-en-v1.5")
    
    client = QdrantClient(url=f"http://{QDRANT_HOST}:{QDRANT_PORT}")

    # 2. Force Reset (Delete and Create)
    if client.collection_exists(COLLECTION_NAME):
        print(f"Deleting existing collection: {COLLECTION_NAME}...")
        client.delete_collection(collection_name=COLLECTION_NAME)

    # 3. Initialize LlamaIndex Qdrant Store
    # Note: LlamaIndex will create the collection automatically with the right dimensions
    vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION_NAME)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    
    print("✅ LlamaIndex + Qdrant Initialized!")
    return storage_context

def seed_data(storage_context):
    file_path="src/qdrant/incidents.json"
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
    storage_ctx = initialize_system()
    idx = seed_data(storage_ctx)
    verify_seeded_data(idx, "Cant login and my new password wont arrive into my email wtff")