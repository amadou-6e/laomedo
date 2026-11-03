# Refactor source history

Exact experiment, selected Skill campaign and historical audit blobs from restored develop and the original integrated refactor are indexed in manifest.json. Existing exact blobs on exp are referenced rather than duplicated. Every entry records its original path, Git revision/blob, byte length and SHA-256. This archive preserves provenance; it does not establish production cleanup, current runnable examples or live acceptance. No production test may import or fetch these campaigns.
