from darknetra.errors import Unavailable


class NullEmbedder:
    name = "unavailable"
    dim = 0
    available = False

    def embed_documents(self, texts):
        raise Unavailable("Embedding model unavailable")

    def embed_query(self, text):
        raise Unavailable("Embedding model unavailable")


def get_embedder():
    # No implicit model downloads or invented vectors in offline deployments.
    return NullEmbedder()
