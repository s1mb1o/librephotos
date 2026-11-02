"""Image similarity sidecar: per-user FAISS indices over the CLIP embeddings.

The indices are kept under BASE_DATA/protected_media/similarity (see
retrieval_index.RetrievalIndex), so a restart of this process no longer
forgets them until the next Calculate CLIP embeddings job.

``POST /build/``
    ``{"user_id", "image_hashes", "image_embeddings"}`` plus, for a rebuild,
    ``"begin": true`` on the first page and ``"commit": true`` on the last:
    the pages fill a staging index that replaces the user's index (on disk,
    then in memory) only once the last page arrived. Without the flags a page
    is added to the live index, as before. Answers ``{"status": true,
    "index_size": n}``, or ``{"status": false, "error": ...}`` with 400.
``DELETE /build/``
    ``{"user_id"}``: forget the user's index, on disk too.
``POST /search/``
    ``{"user_id", "image_embedding", "n"?, "threshold"?}``: ``{"status": true,
    "result": [image hashes]}``; empty for a user without an index.
"""

import os

from flask.typing import ResponseReturnValue
from retrieval_index import IndexBuildError, RetrievalIndex

from librephotos.env import protected_media_root
from service._common import create_app, json_fields, logger, serve_forever

INDEX_ROOT = os.path.join(protected_media_root(), "similarity")

log = logger("image_similarity")

app = create_app("image_similarity")
index = RetrievalIndex(store_dir=INDEX_ROOT)
spaces: dict[str, RetrievalIndex] = {}


def _profile_index(space: object, dimension: object) -> RetrievalIndex:
    if space is None:
        return index
    if (
        not isinstance(space, str)
        or len(space) != 64
        or any(char not in "0123456789abcdef" for char in space)
    ):
        raise ValueError("space must be a SHA-256 profile identifier")
    if isinstance(dimension, bool) or dimension != 1152:
        raise ValueError("SigLIP2 indices require dimension 1152")
    if space not in spaces:
        spaces[space] = RetrievalIndex(
            store_dir=os.path.join(INDEX_ROOT, "spaces", space), dimension=1152
        )
    return spaces[space]


def _user_id(value: object) -> int:
    # The id names a file under INDEX_ROOT, so nothing but an integer will do.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"user_id must be an integer, not {value!r}")
    return value


def _failed(message: str, status: int = 400) -> tuple[dict[str, object], int]:
    log.error(message)
    return {"status": False, "error": message}, status


@app.route("/build/", methods=["POST"])
def build_index() -> ResponseReturnValue:
    user_id, image_hashes, image_embeddings, begin, commit, space, dimension = (
        json_fields(
            "user_id",
            "image_hashes",
            "image_embeddings",
            begin=False,
            commit=False,
            space=None,
            dimension=None,
        )
    )
    try:
        user_id = _user_id(user_id)
        target = _profile_index(space, dimension)
    except ValueError as e:
        return _failed(str(e))

    if not (begin or commit or target.rebuilding(user_id)):
        target.build_index_for_user(user_id, image_hashes, image_embeddings)
        live = target.indices.get(user_id)
        return {"status": True, "index_size": 0 if live is None else live.ntotal}

    try:
        if begin:
            target.begin_rebuild(user_id)
        target.add_to_rebuild(user_id, image_hashes, image_embeddings)
        if not commit:
            return {"status": True, "index_size": target.staged_size(user_id)}
        return {"status": True, "index_size": target.commit_rebuild(user_id)}
    except IndexBuildError as e:
        # A rebuild missing a page must not replace the index.
        target.abandon_rebuild(user_id)
        return _failed(f"rebuild for user {user_id} abandoned: {e}")


@app.route("/build/", methods=["DELETE"])
def delete_index() -> ResponseReturnValue:
    user_id, space, dimension = json_fields("user_id", space=None, dimension=None)
    try:
        user_id = _user_id(user_id)
        _profile_index(space, dimension).remove_user(user_id)
        if space is None:
            root = os.path.join(INDEX_ROOT, "spaces")
            for key in os.listdir(root) if os.path.isdir(root) else []:
                if len(key) == 64 and all(char in "0123456789abcdef" for char in key):
                    _profile_index(key, 1152).remove_user(user_id)
    except ValueError as e:
        return _failed(str(e))
    return {"status": True}


@app.route("/search/", methods=["POST"])
def search_index() -> ResponseReturnValue:
    user_id, image_embedding, n, threshold, space, dimension = json_fields(
        "user_id", "image_embedding", n=100, threshold=27.0, space=None, dimension=None
    )
    try:
        user_id = _user_id(user_id)
        n = int(n)
        threshold = float(threshold)
        target = _profile_index(space, dimension)
    except (TypeError, ValueError) as e:
        return _failed(str(e))
    try:
        result = target.search_similar(user_id, image_embedding, n, threshold)
    except Exception as e:
        log.error("search for user %s failed: %s", user_id, e)
        return {"status": False, "result": [], "error": str(e)}, 500
    return {"status": True, "result": result}


def serve() -> None:
    serve_forever(app, "image_similarity")


if __name__ == "__main__":
    serve()
