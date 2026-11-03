#!/usr/bin/env python3
"""Automatically update mousetricks to the latest Horizon commit (or a given commit).

Fetches the latest commit and matching MIXINS_REV from GitHub, updates all pin
references across the repo, and repacks the .hnmod bundle.

Usage:
    python tools/update_horizon.py            # Update to latest HEAD on main
    python tools/update_horizon.py <commit>   # Update to a specific commit
"""
import json
import pathlib
import re
import subprocess
import sys
import urllib.request

REPO = "horizon-rust/horizon"
ROOT = pathlib.Path(__file__).resolve().parent.parent


def fetch_json(url: str):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "mousetricks-updater", "Accept": "application/vnd.github.v3+json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "mousetricks-updater"})
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8")


def get_commit_info(target: str | None = None):
    if not target or target.lower() in ("latest", "head", "main"):
        url = f"https://api.github.com/repos/{REPO}/commits?per_page=1"
        data = fetch_json(url)
        commit = data[0]
    else:
        url = f"https://api.github.com/repos/{REPO}/commits/{target}"
        commit = fetch_json(url)

    sha = commit["sha"]
    msg = commit["commit"]["message"].splitlines()[0]
    date = commit["commit"]["author"]["date"]
    return sha, msg, date


def get_mixins_rev(horizon_sha: str) -> str:
    url = f"https://raw.githubusercontent.com/{REPO}/{horizon_sha}/launcher/src/native_mods.rs"
    content = fetch_text(url)
    match = re.search(r'pub const MIXINS_REV:\s*&str\s*=\s*"([0-9a-fA-F]{40})";', content)
    if not match:
        raise RuntimeError("Could not find MIXINS_REV in launcher/src/native_mods.rs")
    return match.group(1)


def update_files(horizon_sha: str, mixins_sha: str):
    # 1. horizon-native.json
    manifest_path = ROOT / "horizon-native.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    old_horizon = manifest.get("horizon", "")
    old_mixins = manifest.get("mixins", "")
    manifest["horizon"] = horizon_sha
    manifest["mixins"] = mixins_sha
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    # 2. mixins/mousetricks/horizon-mixin.toml
    mixin_path = ROOT / "mixins" / manifest["id"] / "horizon-mixin.toml"
    mixin_text = mixin_path.read_text(encoding="utf-8")
    if old_horizon and old_horizon in mixin_text:
        mixin_text = mixin_text.replace(old_horizon, horizon_sha)
    else:
        mixin_text = re.sub(
            r'horizon_revision\s*=\s*"[0-9a-fA-F]{40}"',
            f'horizon_revision = "{horizon_sha}"',
            mixin_text,
        )
    mixin_path.write_text(mixin_text, encoding="utf-8")

    # 3. mixins/mousetricks/native.rs
    native_path = ROOT / "mixins" / manifest["id"] / "native.rs"
    native_lines = native_path.read_text(encoding="utf-8").splitlines(keepends=True)
    if native_lines:
        native_lines[0] = re.sub(r"[0-9a-fA-F]{40}", horizon_sha, native_lines[0])
    native_path.write_text("".join(native_lines), encoding="utf-8")

    # 4. README.md
    readme_path = ROOT / "README.md"
    readme_text = readme_path.read_text(encoding="utf-8")
    if old_horizon and old_horizon in readme_text:
        readme_text = readme_text.replace(old_horizon, horizon_sha)
    if old_mixins and old_mixins in readme_text:
        readme_text = readme_text.replace(old_mixins, mixins_sha)
    readme_path.write_text(readme_text, encoding="utf-8")


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"Fetching commit info from {REPO}...")
    horizon_sha, msg, date = get_commit_info(target)
    print(f"Horizon SHA: {horizon_sha}")
    print(f"Date:        {date}")
    print(f"Commit msg:  {msg}")

    print("Fetching matching MIXINS_REV from Horizon launcher...")
    mixins_sha = get_mixins_rev(horizon_sha)
    print(f"Mixins SHA:  {mixins_sha}")

    print("\nUpdating repository files...")
    update_files(horizon_sha, mixins_sha)

    print("Running pack_hnmod.py to verify and pack...")
    res = subprocess.run([sys.executable, str(ROOT / "tools" / "pack_hnmod.py")], check=True)
    if res.returncode == 0:
        print("\nSuccessfully updated and verified!")


if __name__ == "__main__":
    main()
