"""
Upload BRFSS Parquet files to Hugging Face as a public dataset.

Usage:
    uv run python -m scripts.upload_hf
    uv run python -m scripts.upload_hf --token hf_xxx   # non-interactive
"""

import argparse
from pathlib import Path

from huggingface_hub import HfApi, login

REPO_ID = "hesscl/quackrfss"
PARQUET_DIR = Path(__file__).resolve().parent.parent / "data" / "parquet"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", default=None, help="HF write token (prompts if omitted)")
    args = parser.parse_args()

    login(token=args.token)

    api = HfApi()
    api.create_repo(repo_id=REPO_ID, repo_type="dataset", exist_ok=True, private=False)

    parquet_files = sorted(PARQUET_DIR.glob("BRFSS_*.parquet"))
    if not parquet_files:
        print(f"No Parquet files found in {PARQUET_DIR}")
        return

    print(f"Uploading {len(parquet_files)} files to {REPO_ID}...")
    for path in parquet_files:
        print(f"  {path.name}")

    api.upload_folder(
        folder_path=str(PARQUET_DIR),
        path_in_repo="data",
        repo_id=REPO_ID,
        repo_type="dataset",
        allow_patterns="BRFSS_*.parquet",
        commit_message=f"Upload {len(parquet_files)} Parquet files (1990–2024)",
    )

    print(f"\nDone. Dataset live at: https://huggingface.co/datasets/{REPO_ID}")
    print("\nQuery without downloading:")
    print("  import duckdb")
    print(f"  con = duckdb.connect()")
    print(f"  con.sql(\"SELECT * FROM read_parquet('hf://datasets/{REPO_ID}/data/BRFSS_2024.parquet') LIMIT 5\")")


if __name__ == "__main__":
    main()
