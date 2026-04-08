import uuid
from qdrant_client import QdrantClient, models
from fastembed import TextEmbedding, ImageEmbedding
import os
import uuid

import requests

# --- CONFIGURATION ---
COLLECTION_NAME = "incidents"
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))

def initialize_system():
    client = QdrantClient(url=f"http://{QDRANT_HOST}:{QDRANT_PORT}", prefer_grpc=False)

    try:
        client.get_collections()
        print("✅ Qdrant Client Connected!")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return None, None, None

    print("🤖 Loading Embedding Models...")
    t_model = TextEmbedding(model_name="Qdrant/clip-ViT-B-32-text")
    i_model = ImageEmbedding(model_name="Qdrant/clip-ViT-B-32-vision")

    # The modern replacement for recreate_collection
    if not client.collection_exists(COLLECTION_NAME):
        print(f"🛠️ Creating new collection: {COLLECTION_NAME}...")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={
                "text_log": models.VectorParams(size=512, distance=models.Distance.COSINE),
                "dashboard_imgs": models.VectorParams(
                    size=512, 
                    distance=models.Distance.COSINE,
                    multivector_config=models.MultiVectorConfig(
                        comparator=models.MultiVectorComparator.MAX_SIM
                    )
                ),
            }
        )
    else:
        print(f"📚 Collection '{COLLECTION_NAME}' already exists. Skipping creation.")

    return client, t_model, i_model

# TODO: Esto hay que completarlo con data fake util
def seed_data(client, t_model, i_model):
    # Simplified incident list
    incident_data = [
        {
            "description": "Fallo de resolución DNS con el proveedor de SMTP tras múltiples reintentos de inicio de sesión.",
            "images": [] # 0 images
        },
        {
            "description": "Saturación de tablas de estados en el balanceador de carga tras una inundación de paquetes UDP.",
            "images": ["data/screenshots/spike_1.png", "data/screenshots/spike_2.png"] # N images
        },
        {
            "description": "Excepción de puntero nulo en el módulo CheckoutService al intentar calcular el IVA.",
            "images": ["data/screenshots/error_log.png"] # 1 image
        }
    ]

    points = []

    for item in incident_data:
            # 1. Vectorize Text (Always present)
            text_vector = list(t_model.embed([item['description']]))[0]
            
            # 2. Prepare the Vector Dictionary
            # Start with the mandatory text vector
            point_vectors = {
                "text_log": text_vector
            }
            
            # 3. Only add images to the dictionary if they exist
            if item['images']:
                try:
                    image_vectors = list(i_model.embed(item['images']))
                    if image_vectors:
                        point_vectors["dashboard_imgs"] = image_vectors
                except Exception as e:
                    print(f"⚠️ Image embedding failed: {e}")

            # 4. Construct the Point
            points.append(models.PointStruct(
                id=str(uuid.uuid4()),
                vector=point_vectors, # This dict may or may not have 'dashboard_imgs'
                payload={
                    "description": item['description'],
                    "image_paths": item['images']
                }
            ))

    client.upsert(collection_name="incidents", points=points)
    print(f"✅ Seeded {len(points)} incidents (Description + Image Sets).")

if __name__ == "__main__":
    q_client, text_m, img_m = initialize_system()
    if q_client:
        seed_data(q_client, text_m, img_m)