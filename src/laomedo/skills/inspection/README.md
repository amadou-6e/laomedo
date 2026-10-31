# Immutable skill inspection

Inspection reads an exact content-addressed registry revision without constructing
a mutable `SkillStore`, creating a draft or updating latest. The viewer uses this
boundary for current files and for the snapshots underlying historical comparisons.

| Owner | Interface | Responsibility |
| --- | --- | --- |
| `utils.py` | `inspect_skill(root, skill_id, revision_id, include_images=False)` | Verify identity, inventory and hashes, then project bounded file metadata/text and optional verified raster previews |
| `errors.py` | `InspectionError` | Stable safe failure code without paths, payloads or parser output |
| `settings.py` | Fixed limits | File count, directory count/depth, per-file bytes and total bundle bytes |

`inspect` means verify and read; it never imports or executes skill content.
Independent read helpers stay function-only. Registry owns canonical paths and
hashing; the Langflow adapter owns HTTP and the frontend owns presentation.

Reads reject links/reparse points, hard links, nonregular files and oversized
content. Open-descriptor metadata is checked against admission metadata before
reading. Immutable identity and stored file/tree hashes are verified. No `latest`
selection, arbitrary path selection or write API is exposed.

The app presents stable codes through the shared descriptive-error catalogue.
Unsafe, oversized or unavailable immutable revisions require correcting the
selection/source; an unknown read failure can offer a read-only reload. Internal
file-safety controls support, but do not replace, real viewer acceptance.
