"""Where things live. One central sample library shared by every project."""
import os
from pathlib import Path

LIBRARY = Path(os.environ.get("MUSICENGINE_LIBRARY", Path.home() / "SoundLibrary"))
TOOLS = LIBRARY / "_tools"              # downloaded sfizz_render / fluidsynth (Windows only)
NOTE_CACHE = LIBRARY / "_cache" / "notes"
PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parent                   # the source checkout, when the package runs from one
CATALOG_DIR = PACKAGE / "catalog_data"  # shipped inside the package, so `pip install .` works

# License rule: everything a render can contain is public domain (CC0, Unlicense, explicit
# public-domain dedication) or synthesized by this code, so the output belongs entirely to
# the user. CC-BY (attribution) and MIT (notice) are out, as are Sampling Plus, ShareAlike and
# NonCommercial. Sounds synthesized by this engine's own code carry the license "Synthesized".
# The check is a heuristic over each library's declared license plus a keyword scan of its
# license/readme files; it is not legal advice.
ALLOWED_LICENSES = {"CC0-1.0", "Unlicense", "Public-Domain", "Synthesized"}
# Regexes over lower-cased license/readme text found inside a downloaded library. Phrased as
# grants/requirements, because readmes often say "free for commercial and non-commercial use"
# or "credit appreciated but not required", which are fine.
FORBIDDEN_LICENSE_PATTERNS = (
    r"share-?\s?alike", r"\bby-sa\b", r"\bcc[- ]by[- ]sa", r"\bby-nc", r"attribution[- ]non-?commercial",
    r"non-?commercial (use )?only", r"for non-?commercial (use|purposes) only", r"not (be )?(used )?for commercial",
    r"sampling ?(plus|\+)",
    r"creative commons attribution (3|4)\.0", r"\bcc[- ]by[- ]?(3|4)\.0", r"licensed under (the )?cc[- ]by\b",
    r"(must|shall|required to) (give|include|provide) (appropriate )?(credit|attribution)",
    r"permission is hereby granted, free of charge",          # MIT/BSD-style notice requirement
    r"gnu (lesser )?general public license",
)
