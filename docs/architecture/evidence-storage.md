# Evidence object storage

The local evidence backend stores bytes under a key derived from their SHA-256:

```text
sha256/<first two hex>/<next two hex>/<64 lowercase hex>
```

`put_verified` writes bounded chunks to a random file in `.staging`. It fsyncs
the file, changes its mode to `0444`, and promotes it with `os.replace`. On
POSIX, the store fsyncs both directories changed by the cross-directory rename.
It also fsyncs `.staging` after it removes an owned stage on an error or dedup
hit. The root and shard builders create one directory at a time and fsync each
parent that receives a new entry.

`verify(object_key, expected_sha256)` requires the expected digest to equal the
digest encoded in the canonical key. It then hashes the final descriptor and
compares the observed digest with the key digest. A manifest/key disagreement
returns `false` without reading the object. Verification does not change the
stored bytes or expected metadata.

Final entries must be same-device regular files with one hard link. POSIX files
must retain mode `0444`. The store opens POSIX entries with `O_NONBLOCK` and
`O_NOFOLLOW` before checking the descriptor, so a FIFO, device, socket, or
symlink cannot block a worker or pass validation. Mode bits supplement digest
verification; an administrator can still alter a volume.

## Platform boundary

POSIX production uses descriptor-relative directory traversal with
`O_DIRECTORY` and `O_NOFOLLOW`. The constructor fails when the interpreter or
platform lacks those primitives.

`allow_trusted_volume_fallback=True` enables a development backend for a
trusted, stable local volume. The fallback rejects links and reparse points
that exist when it checks a path. It cannot contain a concurrent Windows
junction or reparse-point substitution between that check and a path-based
operation. Production Compose sets
`DARKNETRA_EVIDENCE_STORE_ALLOW_TRUSTED_VOLUME_FALLBACK=false`; API and worker
therefore fail closed if secure traversal is unavailable.

## Task 4 public error mapping

Task 3 exposes internal exceptions only; it adds no HTTP route. Task 4 must map
them to stable public codes without returning `str(exception)`, absolute roots,
shard paths, or random stage names:

| Internal failure | Public code |
|---|---|
| `ObjectKeyError` | `INVALID_OBJECT_KEY` |
| `ObjectHashMismatchError` | `EVIDENCE_HASH_MISMATCH` |
| `ObjectIntegrityError` | `EVIDENCE_OBJECT_INTEGRITY_FAILURE` |
| `ObjectStoreConfigurationError` or filesystem `OSError` | `EVIDENCE_STORE_UNAVAILABLE` |

Logs may retain internal path context under the existing restricted logging
policy. Ordinary settings repr omits `evidence_store_root`.
