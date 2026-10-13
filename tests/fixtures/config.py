"""A minimal configuration directory for tests whose runs need a profile and entries."""

from pathlib import Path

MINIMAL_CONFIG = {
    "profiles/workstation.toml": '[use]\nprefilter = "bm25"\n',
    "providers/search/searxng.toml": 'provider = "searxng"\nbase_url = "http://searx.test"\n',
    "providers/fetch/firecrawl.toml": 'provider = "firecrawl"\nbase_url = "http://crawl.test/v1"\n',
    "providers/llm/agents.toml": 'provider = "openai"\nbase_url = "http://llm.test/v1"\nmodel = "qwen3-14b"\n',
}
"""The profile `workstation` and one entry per block: what the server tests' runs resolve."""


def write_config(config_dir: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (config_dir / name).parent.mkdir(parents=True, exist_ok=True)
        (config_dir / name).write_text(text)
