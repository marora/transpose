"""
LaBSE Embedding Service
Provides HTTP API for generating multilingual sentence embeddings using LaBSE model.

Endpoints:
    POST /embed - Generate embeddings for a list of texts
    GET /health - Health check (returns 200 once model is loaded)
"""

import logging
import sys
from typing import Any

from flask import Flask, jsonify, request
from sentence_transformers import SentenceTransformer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global model instance (loaded once at startup)
model: SentenceTransformer | None = None
model_ready = False


def load_model() -> None:
    """Load LaBSE model into memory at startup."""
    global model, model_ready
    try:
        logger.info("Loading LaBSE model...")
        model = SentenceTransformer("sentence-transformers/LaBSE")
        model_ready = True
        logger.info("LaBSE model loaded successfully (768-dim embeddings, 109 languages)")
    except Exception as e:
        logger.error(f"Failed to load LaBSE model: {e}")
        model_ready = False
        raise


@app.route("/health", methods=["GET"])
def health() -> tuple[dict[str, Any], int]:
    """Health check endpoint. Returns 200 once model is loaded."""
    if model_ready and model is not None:
        return jsonify({"status": "healthy", "model": "LaBSE", "dimensions": 768}), 200
    else:
        return jsonify({"status": "initializing", "model": "LaBSE"}), 503


@app.route("/embed", methods=["POST"])
def embed() -> tuple[dict[str, Any], int]:
    """
    Generate embeddings for a list of texts.

    Request JSON:
        {
            "texts": ["text1", "text2", ...]
        }

    Response JSON:
        {
            "embeddings": [[0.1, 0.2, ...], [0.3, 0.4, ...], ...],
            "count": 2,
            "dimensions": 768
        }
    """
    if not model_ready or model is None:
        return jsonify({"error": "Model not loaded"}), 503

    try:
        data = request.get_json()
        if not data or "texts" not in data:
            return jsonify({"error": "Missing 'texts' field in request"}), 400

        texts = data["texts"]
        if not isinstance(texts, list) or not texts:
            return jsonify({"error": "'texts' must be a non-empty list"}), 400

        # Generate embeddings (returns numpy array)
        embeddings = model.encode(texts, convert_to_numpy=True)

        # Convert numpy array to list for JSON serialization
        embeddings_list = embeddings.tolist()

        return (
            jsonify(
                {
                    "embeddings": embeddings_list,
                    "count": len(embeddings_list),
                    "dimensions": len(embeddings_list[0]) if embeddings_list else 0,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return jsonify({"error": f"Embedding generation failed: {str(e)}"}), 500


# Load model at startup (before first request)
@app.before_request
def ensure_model_loaded() -> None:
    """Ensure model is loaded before handling any request."""
    global model_ready
    if not model_ready:
        load_model()


if __name__ == "__main__":
    # This runs only in development mode (not with gunicorn)
    load_model()
    app.run(host="0.0.0.0", port=8500, debug=False)
