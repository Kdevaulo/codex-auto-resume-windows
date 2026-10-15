"""winget manifests for both editions: the files the owner submits to microsoft/winget-pkgs.

    python build/winget_manifests.py --version 0.6.16 --from-dir <folder with the Setup programs' .sha256 files>
    python build/winget_manifests.py --version 0.6.16 --sha256 standard=<hex> --sha256 advanced=<hex> [--out DIR]

For each edition this writes the community repository's multi-file manifest - version, installer, the
en-US default locale and a ko-KR locale - under <out>/manifests/s/<publisher>/<package>/<version>/, the
folder layout the repository asks for. Nothing is downloaded and nothing is sent anywhere; submitting the
files is a public pull request the owner makes (docs/WINGET.md).

What goes in comes from scripts/release.json and .codex-plugin/plugin.json: the download address, the
file names and the names people see. The installer a package points at is the edition's one-file Setup
program (build/make_setup.py), not the ZIP: winget runs an installer, and the ZIP's Install.cmd is none
of the types it can run from inside an archive. release.json pins the ZIP archives and not the Setup
programs, so a Setup program's SHA-256 is read from the .sha256 file published beside it - the release
workflow writes `<sha256>  <name>`, as build/make_release.py does for every file. The archive's pin is
still required: a version whose archive has no pin yet has not had its published digest checked
(docs/CONTRIBUTING.md, "After a release is published"), and no manifests are made for it.

The silent switch is the one thing that does not exist yet. winget's community repository accepts an
installer only if it installs without a person, and Install.cmd ends in `pause` whatever it is given
(outputs/plans/v0616-winget/GAPS.md says what the smallest change is). UNATTENDED_FROM names the first
version whose Setup program has it; until it is set, this writes nothing without --draft, so a manifest
that cannot pass is not made by accident. UNATTENDED_SWITCH is the proposed switch.

The YAML is written by hand, without a YAML library: every value is a double-quoted string, which is what
a JSON string also is, and the structure is the few shapes the schema needs here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import legacy_bootstraps  # noqa: E402  (the version rule, `order`)
import make_setup  # noqa: E402  (the Setup programs' file names)

# The manifest schema these files follow. 1.12.0 has every field used here and is the one Microsoft's own
# examples use; the repository's current schema, 1.28.0, adds two fields this does not write (Icons,
# DesiredStateConfiguration), so the files satisfy both.
SCHEMA = "1.12.0"
# The publisher segment of both package identifiers: the GitHub owner the product is published under, which is
# also the author in the plugin manifest and the Publisher field below. A segment may hold a hyphen.
PUBLISHER = "songyb111-gachon"
# The first version whose Setup program installs without anyone answering (GAPS.md). None until it exists.
UNATTENDED_FROM = None
# The proposed switch: the Setup program takes it, does not pass it on, and runs Install.cmd and install.ps1
# in an unattended mode that ends without `pause` or a question.
UNATTENDED_SWITCH = "-Silent"
# What Install.cmd ends with when the other edition is installed: install.ps1's EDITION_CHANGE_REFUSED.
EDITION_CHANGE_REFUSED = 14
LOCALES = ("en-US", "ko-KR")
EDITIONS = ("standard", "advanced")
SUFFIX = {"standard": "CodexAutoResume", "advanced": "CodexAutoResume.Advanced"}
SHORT = "Waits out a Codex usage limit, then continues the same conversation."
SHORT_KO = "Codex \uc791\uc5c5\uc774 \uc0ac\uc6a9\ub7c9 \ud55c\ub3c4\ub85c \uba48\ucd94\uba74 \ud55c\ub3c4\uac00 \ud480\ub9b4 \ub54c\uae4c\uc9c0 \uae30\ub2e4\ub838\ub2e4\uac00 \uac19\uc740 \ub300\ud654\ub97c \uc774\uc5b4 \uac11\ub2c8\ub2e4."
LONG = ("A Windows watcher for the Codex desktop app. When a task stops because of a usage limit, a rate limit or a "
        "temporary failure, it waits until it is safe again and continues that exact conversation. It installs "
        "for your Windows user only and needs no administrator rights.")
LONG_KO = "Windows\uc6a9 \uac10\uc2dc \ud504\ub85c\uadf8\ub7a8\uc785\ub2c8\ub2e4. Codex \ub370\uc2a4\ud06c\ud1b1 \uc571\uc758 \uc791\uc5c5\uc774 \uc0ac\uc6a9\ub7c9 \ud55c\ub3c4, \uc18d\ub3c4 \uc81c\ud55c \ub610\ub294 \uc77c\uc2dc\uc801\uc778 \uc624\ub958\ub85c \uba48\ucd94\uba74, \uc548\uc804\ud574\uc9c8 \ub54c\uae4c\uc9c0 \uae30\ub2e4\ub9b0 \ub4a4 \uac19\uc740 \ub300\ud654\ub97c \uadf8\ub300\ub85c \uc774\uc5b4 \uac11\ub2c8\ub2e4. \ud604\uc7ac Windows \uc0ac\uc6a9\uc790 \uacc4\uc815\uc5d0\ub9cc \uc124\uce58\ub418\uace0 \uad00\ub9ac\uc790 \uad8c\ud55c\uc774 \ud544\uc694 \uc5c6\uc2b5\ub2c8\ub2e4."
ADVANCED_NOTE = " The advanced edition is the standard edition plus features you turn on yourself."
ADVANCED_NOTE_KO = " \uace0\uae09\ud310\uc740 \ud45c\uc900\ud310\uc5d0 \ub354\ud574, \uc9c1\uc811 \ucf1c\uc11c \uc4f0\ub294 \uae30\ub2a5\uc744 \ub2f4\uc740 \ud310\uc785\ub2c8\ub2e4."
TAGS = ("codex", "auto-resume", "auto-retry", "usage-limit", "rate-limit", "watcher", "windows", "developer-tools")
BLOB = "https://github.com/{owner}/{repo}/blob/main/{path}"


def package_id(edition: str) -> str:
    return "%s.%s" % (PUBLISHER, SUFFIX[edition])


def folder(edition: str, version: str) -> Path:
    """manifests / <first letter of the publisher, lower case> / <publisher> / <package...> / <version>."""
    parts = package_id(edition).split(".")
    return Path("manifests", parts[0][0].lower(), *parts, version)


def final_version(version: str) -> bool:
    """A winget package is a release: X.Y.Z, never a pre-release."""
    return re.fullmatch(r"\d+\.\d+\.\d+", version) is not None


def plugin_manifest(root: Path) -> dict:
    return json.loads((root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8-sig"))


def display_name(edition: str, root: Path = ROOT) -> str:
    name = str(plugin_manifest(root)["interface"]["displayName"])
    return name if edition == "standard" else "%s %s" % (name, make_setup.WORDS["advanced"])


def installer_url(release: dict, edition: str, version: str) -> str:
    return release["download"].replace("{version}", version) + make_setup.setup_name(edition, version)


def pinned(release: dict, edition: str, version: str) -> bool:
    table = release["sha256"] if edition == "standard" else release.get("advanced", {}).get("sha256", {})
    return bool(table.get(version))


def read_sidecar(directory: Path, edition: str, version: str) -> str:
    """The digest in `<sha256>  <name>`, the .sha256 file published beside the Setup program."""
    name = make_setup.setup_name(edition, version)
    path = directory / (name + ".sha256")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as error:
        raise SystemExit("cannot read %s: %s" % (path, error))
    fields = text.split()
    if len(fields) != 2 or fields[1].lstrip("*") != name:
        raise SystemExit("%s is not `<sha256>  %s`" % (path, name))
    return fields[0]


# ------------------------------------------------------------------------------------------------ the YAML

def _scalar(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def emit(mapping: dict, indent: int = 0) -> list[str]:
    """Block-style YAML for a mapping of strings, lists of strings, lists of mappings and nested mappings."""
    lines = []
    pad = " " * indent
    for key, value in mapping.items():
        if isinstance(value, dict):
            lines.append("%s%s:" % (pad, key))
            lines.extend(emit(value, indent + 2))
        elif isinstance(value, list):
            lines.append("%s%s:" % (pad, key))
            for item in value:
                if isinstance(item, dict):
                    body = emit(item, indent + 2)
                    lines.append("%s- %s" % (pad, body[0].lstrip()))
                    lines.extend(body[1:])
                else:
                    lines.append("%s- %s" % (pad, _scalar(item)))
        else:
            lines.append("%s%s: %s" % (pad, key, _scalar(value)))
    return lines


def render(mapping: dict, kind: str) -> str:
    """One manifest file's text: the language-server header the repository's tools write, the fields, CRLF."""
    header = ["# Created using build/winget_manifests.py",
              "# yaml-language-server: $schema=https://aka.ms/winget-manifest.%s.%s.schema.json" % (kind, SCHEMA)]
    return "\r\n".join(header + emit(mapping)) + "\r\n"


# ------------------------------------------------------------------------------------------------ the files

def _base(edition: str, version: str) -> dict:
    return {"PackageIdentifier": package_id(edition), "PackageVersion": version}


def _trailer(kind: str) -> dict:
    return {"ManifestType": kind, "ManifestVersion": SCHEMA}


def version_manifest(edition: str, version: str) -> dict:
    return {**_base(edition, version), "DefaultLocale": "en-US", **_trailer("version")}


def installer_manifest(release: dict, edition: str, version: str, digest: str, root: Path = ROOT) -> dict:
    author = str(plugin_manifest(root)["author"]["name"])
    url = BLOB.format(owner=release["owner"], repo=release["repo"], path="docs/EDITIONS.md")
    return {
        **_base(edition, version),
        "InstallerLocale": "en-US",
        "Platform": ["Windows.Desktop"],
        "MinimumOSVersion": "10.0.0.0",
        "InstallerType": "exe",
        "Scope": "user",
        "InstallModes": ["interactive", "silent", "silentWithProgress"],
        "InstallerSwitches": {"Silent": UNATTENDED_SWITCH, "SilentWithProgress": UNATTENDED_SWITCH},
        "ExpectedReturnCodes": [{"InstallerReturnCode": str(EDITION_CHANGE_REFUSED), "ReturnResponse": "custom",
                                 "ReturnResponseUrl": url}],
        "UpgradeBehavior": "install",
        "ElevationRequirement": "elevationProhibited",
        "AppsAndFeaturesEntries": [{"DisplayName": display_name(edition, root), "Publisher": author,
                                    "DisplayVersion": version, "InstallerType": "exe"}],
        "Installers": [{"Architecture": "x64",
                        "InstallerUrl": installer_url(release, edition, version),
                        "InstallerSha256": digest.upper()}],
        **_trailer("installer"),
    }


def _locale_fields(release: dict, edition: str, version: str, locale: str, root: Path) -> dict:
    owner, repo = release["owner"], release["repo"]
    repository = "https://github.com/%s/%s" % (owner, repo)
    advanced = edition == "advanced"
    if locale == "en-US":
        short, long_ = SHORT, LONG + (ADVANCED_NOTE if advanced else "")
    else:
        short, long_ = SHORT_KO, LONG_KO + (ADVANCED_NOTE_KO if advanced else "")
    return {
        **_base(edition, version),
        "PackageLocale": locale,
        "Publisher": PUBLISHER,
        "PublisherUrl": "https://github.com/%s" % owner,
        "PublisherSupportUrl": repository + "/issues",
        "PrivacyUrl": BLOB.format(owner=owner, repo=repo, path="docs/PRIVACY.md"),
        "PackageName": display_name(edition, root),
        "PackageUrl": repository,
        "License": "MIT",
        "LicenseUrl": BLOB.format(owner=owner, repo=repo, path="LICENSE"),
        "ShortDescription": short,
        "Description": long_,
        "Tags": list(TAGS),
        "ReleaseNotesUrl": "%s/releases/tag/v%s" % (repository, version),
    }


def default_locale_manifest(release: dict, edition: str, version: str, root: Path = ROOT) -> dict:
    return {**_locale_fields(release, edition, version, "en-US", root), **_trailer("defaultLocale")}


def locale_manifest(release: dict, edition: str, version: str, locale: str, root: Path = ROOT) -> dict:
    """An additional locale: the schema asks only for the identifier, the version and the locale, and shows
    the default locale's value for any field left out - so only what is translated is written."""
    full = _locale_fields(release, edition, version, locale, root)
    keep = ("PackageIdentifier", "PackageVersion", "PackageLocale", "Publisher", "ShortDescription", "Description")
    return {**{key: full[key] for key in keep}, **_trailer("locale")}


def manifests(release: dict, edition: str, version: str, digest: str, root: Path = ROOT) -> dict:
    """{file name: text} for one edition, named the way the repository asks: <identifier>.<kind>.yaml."""
    ident = package_id(edition)
    files = {
        ident + ".yaml": render(version_manifest(edition, version), "version"),
        ident + ".installer.yaml": render(installer_manifest(release, edition, version, digest, root), "installer"),
        ident + ".locale.en-US.yaml": render(default_locale_manifest(release, edition, version, root),
                                             "defaultLocale"),
    }
    for locale in LOCALES[1:]:
        files["%s.locale.%s.yaml" % (ident, locale)] = render(locale_manifest(release, edition, version, locale, root),
                                                              "locale")
    return files


def build(version: str, digests: dict, out: Path, draft: bool = False, release: dict | None = None,
          root: Path = ROOT) -> list[Path]:
    """Writes both editions' manifests under `out`; returns the files. Refuses what cannot be submitted."""
    release = release or json.loads((root / "scripts" / "release.json").read_text(encoding="utf-8-sig"))
    if not final_version(version):
        raise SystemExit("%s is not a release (X.Y.Z): winget packages are releases, never pre-releases." % version)
    for edition in EDITIONS:
        if not pinned(release, edition, version) and not draft:
            raise SystemExit("the %s archive of %s has no digest in scripts/release.json yet: pin the published "
                             "release first (docs/CONTRIBUTING.md), then make the manifests." % (edition, version))
        if not re.fullmatch(r"[A-Fa-f0-9]{64}", digests.get(edition, "")):
            raise SystemExit("no SHA-256 for the %s Setup program" % edition)
    if not draft and (UNATTENDED_FROM is None or
                      legacy_bootstraps.order(version) < legacy_bootstraps.order(UNATTENDED_FROM)):
        raise SystemExit("the Setup program of %s has no unattended mode, and winget accepts no installer that "
                         "needs a person (outputs/plans/v0616-winget/GAPS.md). Write the files anyway, to look at, "
                         "with --draft." % version)
    written = []
    for edition in EDITIONS:
        target = out / folder(edition, version)
        target.mkdir(parents=True, exist_ok=True)
        for name, text in manifests(release, edition, version, digests[edition], root).items():
            path = target / name
            path.write_bytes(text.encode("utf-8"))
            written.append(path)
    return written


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--version", required=True, help="the release, X.Y.Z")
    parser.add_argument("--from-dir", type=Path, help="a folder holding the Setup programs' .sha256 files")
    parser.add_argument("--sha256", action="append", default=[], metavar="EDITION=HEX",
                        help="a Setup program's SHA-256 by hand, per edition")
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "dist" / "winget")
    parser.add_argument("--draft", action="store_true",
                        help="write the files although the Setup program has no unattended mode or the archive "
                             "is not pinned yet")
    arguments = parser.parse_args(argv)
    digests = {}
    for item in arguments.sha256:
        edition, _, value = item.partition("=")
        if edition not in EDITIONS:
            parser.error("--sha256 takes standard=<hex> or advanced=<hex>")
        digests[edition] = value
    if arguments.from_dir:
        for edition in EDITIONS:
            if edition not in digests:
                digests[edition] = read_sidecar(arguments.from_dir, edition, arguments.version)
    for path in build(arguments.version, digests, arguments.out, draft=arguments.draft):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
