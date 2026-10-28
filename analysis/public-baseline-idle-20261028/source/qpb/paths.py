from pathlib import Path


def tool_root() -> Path:
    return Path(__file__).resolve().parents[1]


def data_dir(root: Path | None = None) -> Path:
    return (root or tool_root()) / "data"


def manifest_dir(root: Path | None = None) -> Path:
    return (root or tool_root()) / "manifests"


def config_dir(root: Path | None = None) -> Path:
    return (root or tool_root()) / "config"
