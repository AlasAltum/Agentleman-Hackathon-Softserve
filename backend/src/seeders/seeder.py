import os
import uuid
from qdrant_client import QdrantClient
from llama_index.core import VectorStoreIndex, StorageContext, Document
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.embeddings.fastembed import FastEmbedEmbedding
from llama_index.core import Settings
import json
import psycopg2
from psycopg2 import sql

# --- CONFIGURATION ---
COLLECTION_NAME = "incidents"
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))

# Postgres Configuration
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_BDNAME", "postgres")

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

def initialize_postgres():
    """Initialize PostgreSQL connection and create incidents table if it doesn't exist."""
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            database=POSTGRES_DB
        )
        cursor = conn.cursor()
        
        # Create incidents table if it doesn't exist
        create_table_query = """
        CREATE TABLE IF NOT EXISTS incidents (
            id VARCHAR(50) PRIMARY KEY,
            description TEXT NOT NULL,
            resolution TEXT,
            image_path VARCHAR(500),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        cursor.execute(create_table_query)
        conn.commit()
        print("✅ PostgreSQL Connected & incidents table ensured!")
        
        return conn, cursor
    except psycopg2.Error as e:
        print(f"❌ PostgreSQL Connection Error: {e}")
        return None, None

def seed_data(storage_context, cursor=None):
    file_path=os.path.join(os.path.dirname(__file__), "incidents.json")
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
    postgres_count = 0
    
    for item in incident_data:
        metadata = {
            "incident_id": item["id"],
            "summary": item["description"],
            "resolution": item.get("resolution", ""),
            "timestamp": "2026-04-08T10:00:00Z"
        }
        
        # Handle optional image
        image_path = item.get("image_path")
        if image_path:
            # Resolve image path relative to setup.py directory
            resolved_image_path = os.path.join(os.path.dirname(__file__), image_path)
            if os.path.exists(resolved_image_path):
                metadata["image_path"] = image_path
                print(f"  ℹ️  Image found for {item['id']}: {image_path}")
            else:
                print(f"  ⚠️  Warning: Image path specified for {item['id']} but file not found: {resolved_image_path}")
        
        # LlamaIndex wraps data into Document objects
        doc = Document(
            text=item["description"],
            doc_id=item["id"],
            metadata=metadata
        )
        documents.append(doc)
        
        # Seed to PostgreSQL
        if cursor:
            try:
                insert_query = """
                INSERT INTO incidents (id, description, resolution, image_path)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    description = EXCLUDED.description,
                    resolution = EXCLUDED.resolution,
                    image_path = EXCLUDED.image_path
                """
                cursor.execute(insert_query, (
                    item["id"],
                    item["description"],
                    item.get("resolution", ""),
                    image_path
                ))
                postgres_count += 1
            except psycopg2.Error as e:
                print(f"  ❌ Error inserting {item['id']} into PostgreSQL: {e}")

    # This one line handles embedding AND upserting to Qdrant
    index = VectorStoreIndex.from_documents(
        documents, storage_context=storage_context
    )
    print(f"✅ Seeded {len(documents)} incidents into Qdrant Vector DB.")
    if cursor:
        print(f"✅ Seeded {postgres_count} incidents into PostgreSQL.")
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
    # Initialize Qdrant
    storage_ctx = initialize_system()
    
    # Initialize PostgreSQL
    conn, cursor = initialize_postgres()
    
    # Seed data to both databases
    idx = seed_data(storage_ctx, cursor)
    
    # Commit PostgreSQL changes
    if conn and cursor:
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ PostgreSQL connection closed.")
    
    # Verify Qdrant seeded data
    verify_seeded_data(idx, "Cant login and my new password wont arrive into my email wtff")