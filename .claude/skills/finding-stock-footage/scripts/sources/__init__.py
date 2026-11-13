"""Stock source adapters, one module per source, configured by sources.json.

Adding a source: write sources/<slug>.py with SLUG, NEEDS_KEY and a Source(cfg, key, http) class whose
search(query, orientation) yields model.Candidate objects; add {"slug", "url", "priority", "isEnabled"} to
sources.json. The key comes from the environment variable <SLUG>_API_KEY.
"""
import importlib
import json


def key_name(slug):
    return f"{slug.upper()}_API_KEY"


def load_sources(config_path, env, http, only=None):
    """(enabled adapters sorted by priority, notes about skipped sources)."""
    with open(config_path, encoding="utf-8") as f:
        entries = json.load(f)["sources"]
    sources, notes = [], []
    for cfg in entries:
        slug = cfg["slug"]
        if not cfg.get("isEnabled") or (only is not None and slug not in only):
            continue
        try:
            module = importlib.import_module(f"sources.{slug}")
        except ModuleNotFoundError:
            notes.append(f"{slug}: bu kaynak için kod yok, atlandı")
            continue
        key = env.get(key_name(slug)) or None
        if module.NEEDS_KEY and not key:
            notes.append(f"{slug}: {key_name(slug)} yok, atlandı")
            continue
        sources.append(module.Source(cfg, key, http))
    sources.sort(key=lambda s: s.priority)
    return sources, notes
