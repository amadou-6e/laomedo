# Agent example and campaign history

Exact original develop Git blobs recorded in manifest.json, preserved before production consolidation. Historical results retain their original scope; these files do not verify the assembled Agent implementation. Archives are not imported by production tests and exp is never merged wholesale into develop.

Original `.gitattributes` files use the non-active `.gitattributes.source` archive name so they cannot alter sibling archived bytes. The manifest maps every original path to its archive path. The archive disables text normalization; preservation is verified against committed Git blobs, not just working files.
