"""Check release file completeness and reject private/runtime data in distributions."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import zipfile


PACKAGE_FILES = {"moss_go/__main__.py", "moss_go/model_setup.py", "moss_go/examples.py",
                 "moss_go/web/index.html", "moss_go/web/app.js", "moss_go/web/examples.js",
                 "moss_go/web/studio.css", "moss_go/web/fonts/InterVariable.woff2", "moss_go/web/fonts/OFL.txt",
                 "moss_go/nodes/THIRD_PARTY_OSTRIS_LICENSE.txt", "moss_go/assets/assistant_model.json",
                 "moss_go/assets/model_manifest.json", "moss_go/assets/character_catalog.json",
                 "moss_go/assets/illustrated_examples.json", *{f"moss_go/web/examples/{name}.png" for name in ("mira", "theo", "nia")}}
ROOT = Path(__file__).resolve().parents[1]
PACKAGE_FILES.update(path.relative_to(ROOT).as_posix() for path in (ROOT / "moss_go").rglob("*")
                     if path.is_file() and path.suffix in {".py", ".js", ".css", ".svg", ".txt", ".json", ".woff2", ".png", ".jpg", ".webp"})
SOURCE_FILES = {"__init__.py", "run.py", "models.py", "run_tests.py", "README.md", "LICENSE",
                "THIRD_PARTY_NOTICES.md", "pyproject.toml", "requirements.lock", "build-requirements.lock",
                "uv.lock", "package-lock.json", "scripts/check_install.py", "scripts/installed_smoke.py",
                "scripts/check_archives.py", "tests/test_examples.py", "docs/MODELS.md", "docs/SUBMISSION_RU.md"}
SOURCE_FILES.update({"CHANGELOG.md", "docs/RELEASE_NOTES.md", "docs/MANUAL_CHECK_RU.md", "workflows/README.md",
                     "workflows/moss-create-api.json", "workflows/flux-create-api.json", "workflows/flux-reference-api.json",
                     "workflows/flux-masked-refine-api.json", "workflows/mira-edit-mask.png"})


def check(files, read, required):
    names = set(files)
    absent = required - names
    if absent:
        raise ValueError("Missing distribution files: " + ", ".join(sorted(absent)))
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            raise ValueError("Unexpected archive path: " + name)
        if set(path.parts) & {".local", ".git", "node_modules", "data", "__pycache__"} or path.suffix in {".safetensors", ".sqlite3", ".pyc", ".log"} or path.name in {".env", "PROJECT_STATUS.md"}:
            raise ValueError("Private or runtime data in distribution: " + name)
    examples = json.loads(read("moss_go/assets/illustrated_examples.json"))
    assert len(examples["images"]) == 3
    for item in examples["images"]:
        digest = hashlib.sha256(read("moss_go/web/examples/" + item["filename"])).hexdigest()
        assert digest == item["sha256"], item["id"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    wheels, sources = list(args.directory.glob("moss_go-*.whl")), list(args.directory.glob("moss_go-*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        parser.error("Expected one wheel and one source distribution.")
    with zipfile.ZipFile(wheels[0]) as archive:
        check(archive.namelist(), archive.read, PACKAGE_FILES)
        assert any(name.endswith("/licenses/THIRD_PARTY_NOTICES.md") for name in archive.namelist())
    with tarfile.open(sources[0], "r:gz") as archive:
        members = archive.getmembers()
        assert not any(member.issym() or member.islnk() for member in members)
        prefix = members[0].name.split("/")[0] + "/"
        names = [member.name[len(prefix):] for member in members if member.isfile()]
        assert all(member.name.startswith(prefix) for member in members if member.isfile())
        check(names, lambda name: archive.extractfile(prefix + name).read(), PACKAGE_FILES | SOURCE_FILES)
    print(f"Archive checks passed: {wheels[0].name}, {sources[0].name}")


if __name__ == "__main__":
    main()
