from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent

def load_config(path: Path | None = None) -> dict:
    path = path or ROOT / "spec_inputs.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def all_tickers(cfg: dict) -> list[str]:
    """Return deduplicated ordered list of every ticker across all universes."""
    seen: set[str] = set()
    out: list[str] = []
    for univ in cfg["universes"].values():
        for t in univ["risky"] + univ["safe"]:
            if t not in seen:
                seen.add(t)
                out.append(t)
    return out
