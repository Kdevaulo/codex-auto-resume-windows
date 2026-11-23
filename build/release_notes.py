"""Extract one version's section from docs/CHANGELOG.md, for the GitHub release body.

The changelog is the only place release notes are written, so the published notes cannot
drift from the repository's own history: there is nothing to keep in step.

It fails rather than inventing anything. A tag whose version has no changelog section is
a mistake worth stopping the release for, not something to paper over with a generated
list of commit subjects.

The changelog lives in docs/ since the front page was tidied, and its relative links are
written from there (`GUIDE.md`, `../README.md`). A release body is not in docs/: GitHub
resolves a relative link in it from the repository's root. So each relative link is rebased
to the root on the way out - left as written, every link in every release body from then on
would have pointed one folder too high.
"""
from __future__ import annotations

import argparse
import ast
import json
import posixpath
from pathlib import Path
import re
import sys

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import make_setup  # noqa: E402  (the one place that names the setup programs)

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "docs" / "CHANGELOG.md"
# The folder the changelog's relative links are written from, as the root sees it.
WRITTEN_FROM = "docs"

CODE = re.compile("(```.*?```|~~~.*?~~~|`[^`\n]*`)", re.S)
LINK = re.compile(r'(\]\(\s*)([^)\s]+)(\s*\))|((?:href|src)=")([^"]+)(")')


def rebase(body: str, folder: str = WRITTEN_FROM) -> str:
    """Relative links written from `folder`, re-expressed from the repository's root. Absolute
    URLs, anchors, and anything inside code are left as they are."""
    def fix(target: str) -> str:
        if re.match(r"^[a-zA-Z][\w+.-]*:", target) or target.startswith(("#", "/")):
            return target
        path, hashmark, fragment = target.partition("#")
        if not path:
            return target
        rooted = posixpath.normpath(posixpath.join(folder, path))
        if rooted.startswith(".."):
            return target
        return rooted + (hashmark + fragment if hashmark else "")

    def one(found):
        if found.group(2) is not None:
            return found.group(1) + fix(found.group(2)) + found.group(3)
        return found.group(4) + fix(found.group(5)) + found.group(6)

    return "".join(part if index % 2 else LINK.sub(one, part)
                   for index, part in enumerate(CODE.split(body)))


def section(text: str, version: str) -> str:
    """The body under `## v<version> ...`, up to the next top-level entry.

    A pre-release's heading - `## v0.6.6-beta` - is an entry of its own, and never the release's:
    the version has to end where the heading's version does, so neither a suffix nor a longer
    number is read as a match, wherever in the file the pre-release sits."""
    wanted = re.escape(str(version).lstrip("v"))
    pattern = re.compile(r"^##\s+v%s(?![\w.-]).*?$" % wanted, re.MULTILINE)
    match = pattern.search(text)
    if match is None:
        raise SystemExit("CHANGELOG.md has no section for v%s" % version)
    rest = text[match.end():]
    following = re.search(r"^##\s+v", rest, re.MULTILINE)
    body = rest[:following.start()] if following else rest
    body = body.strip("\n")
    if not body:
        raise SystemExit("the CHANGELOG.md section for v%s is empty" % version)
    return body


REPO = "https://github.com/songyb111-gachon/codex-auto-resume-windows"

# The first paragraph of every entry: `> **Short title.** One sentence on what the release set out to do.`
# The title is what follows the version in the release's own title on GitHub.
LEAD = re.compile(r"^> \*\*([^*\n]+?)\.\*\* \S", re.MULTILINE)


def short_title(text: str, version: str) -> str:
    """The short title in the first paragraph of `## v<version>`'s entry; fails when the entry does not
    open with one - a release without its title is a mistake worth stopping the release for."""
    first = section(text, version).lstrip("\n").split("\n", 1)[0]
    found = LEAD.match(first)
    if found is None:
        raise SystemExit("the CHANGELOG.md section for v%s does not open with its title line "
                         "(> **Short title.** One sentence.)" % str(version).lstrip("v"))
    return found.group(1)


def release_title(text: str, version: str) -> str:
    """The title of the GitHub release: `v<version> — <short title>`."""
    return "v%s — %s" % (str(version).lstrip("v"), short_title(text, version))


# The second paragraph of every entry, right under the title line: what kind of release it is, every kind that
# applies, biggest first - `**Kind:** New features · Design changes · Bug fixes`, and in the Korean changelog
# `**성격:** 기능 추가 · 디자인 수정 · 버그 수정`. This table is the one vocabulary: English word -> its Korean
# twin. A word that is not in it is a mistake, not a new kind.
KINDS = {
    "New features": "기능 추가",
    "Feature changes": "기능 수정",
    "Bug fixes": "버그 수정",
    "New design": "디자인 추가",
    "Design changes": "디자인 수정",
    "Performance": "성능 개선",
    "Security": "보안 수정",
    "Languages": "언어·번역",
    "Under the hood": "내부 정리",
}
KIND_SEPARATOR = " · "
KIND_LINE = re.compile(r"^\*\*(Kind|성격):\*\* (\S.*)$")


def kinds(text: str, version: str) -> list:
    """The kinds in the second paragraph of `## v<version>`'s entry, as English words in the order written.

    The line is `**Kind:** A · B` in the English changelog and `**성격:** 가 · 나` in the Korean one; either is read
    and a Korean word is given back as its English twin. Fails when the entry has no such paragraph, names a
    word that is not in KINDS (or one of the other language's), or names one twice - a release without its
    kind is a mistake worth stopping for."""
    number = str(version).lstrip("v")
    paragraphs = re.split(r"\n\s*\n", section(text, version))
    found = KIND_LINE.match(paragraphs[1].strip()) if len(paragraphs) > 1 else None
    if found is None:
        raise SystemExit("the CHANGELOG.md section for v%s has no kind line as its second paragraph "
                         "(**Kind:** New features · Bug fixes)" % number)
    table = KINDS if found.group(1) == "Kind" else {twin: english for english, twin in KINDS.items()}
    names = []
    for word in found.group(2).split(KIND_SEPARATOR):
        if word not in table:
            raise SystemExit("the CHANGELOG.md section for v%s names the kind %r, which is not one of: %s"
                             % (number, word, ", ".join(table)))
        name = word if found.group(1) == "Kind" else table[word]
        if name in names:
            raise SystemExit("the CHANGELOG.md section for v%s names the kind %r twice" % (number, word))
        names.append(name)
    return names


def download_block(version: str) -> str:
    """The first lines of every release page: direct links to the tag's two setup programs, so
    nobody has to scroll to Assets. The file names come from make_setup, which builds them."""
    version = str(version).lstrip("v")
    tag = "v" + version

    def link(label, edition):
        return "[%s edition \u2014 Setup.exe](%s/releases/download/%s/%s)" % (
            label, REPO, tag, make_setup.setup_name(edition, version))

    return ("**\u2b07 Download:** %s \u00b7 %s\n"
            "<sub>Run the one you want. The ZIP archives and their SHA-256 files are under Assets below; "
            "how to check them: [VERIFY.md](%s/blob/main/docs/VERIFY.md).</sub>\n"
            % (link("Standard", "standard"), link("Advanced", "advanced"), REPO))


# The longest release body this project publishes (the car-release checklist's rule, held here since v0.6.26, audit4 F4):
# GitHub itself refuses a body over 125,000 characters, and only once the release is being made; the margin keeps a body
# that grows on the way clear of that refusal. The largest so far is v0.6.11's, 58,350 characters.
BODY_MAX = 100000


def notes(text: str, version: str) -> str:
    """The release body: the download block, a blank line, then the rebased changelog section.

    Refused (ValueError) over BODY_MAX characters, so the release workflow stops at its notes step, before anything is
    published, rather than at GitHub's refusal."""
    body = download_block(version) + "\n" + rebase(section(text, version))
    if len(body) > BODY_MAX:
        raise ValueError("the release notes of %s are %d characters, over the %d a release body may have: shorten "
                         "the changelog entry" % (version, len(body), BODY_MAX))
    named = hidden_named(body)
    if named:
        raise ValueError("the release notes of %s name %r, a special day or a hidden press, which stay out of every "
                         "release body: take it out of the changelog entry" % (version, named))
    return body


# The special days and the hidden presses stay out of the release notes as out of every document (the owner, 2026-11-16;
# audit4 F4). The words are taken from the code, not written here: brand/days.py's DAY_LOOKS (each day's name, as written
# and with a space or a hyphen for its underscore, and its colours), the catalogs' status.aside keys and every sentence
# they give in every language, and the phrases tests/test_gui_v0623_days.py already keeps out of the documents
# (HIDDEN_PHRASES, held to that test by tests/test_release_notes_hidden.py). A word counts only whole, in any case, so
# "day", "press" or "Monday" are never refused.
DAYS_SOURCE = ROOT / "src" / "codex_auto_resume" / "brand" / "days.py"
CATALOGS = ROOT / "src" / "codex_auto_resume" / "locales"
ASIDE = "status.aside"
HIDDEN_PHRASES = ("pick it up", "이어 둘게요")


def day_looks() -> dict:
    """DAY_LOOKS as days.py writes it, read without importing the product."""
    tree = ast.parse(DAYS_SOURCE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "DAY_LOOKS" for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit("brand/days.py has no DAY_LOOKS")


def hidden_words() -> tuple:
    """Every word and phrase a release body may not name, longest first."""
    words = set(HIDDEN_PHRASES)
    for day, colours in day_looks().items():
        words.update((day, day.replace("_", " "), day.replace("_", "-")))
        words.update(colours)
    for catalog in sorted(CATALOGS.glob("*.json")):
        for key, value in json.loads(catalog.read_text(encoding="utf-8")).items():
            if key == ASIDE or key.startswith(ASIDE + "_"):
                words.add(key)
                if isinstance(value, str) and "{" not in value and value.strip():
                    words.add(value.strip())
    return tuple(sorted(words, key=lambda word: (-len(word), word)))


def hidden_named(body: str):
    """The first special day or hidden press `body` names, whole and in any case, or None."""
    for word in hidden_words():
        if re.search(r"(?<!\w)%s(?!\w)" % re.escape(word), body, re.IGNORECASE):
            return word
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Print a version's changelog section.")
    parser.add_argument("version", help="version, with or without a leading v")
    parser.add_argument("--changelog", default=str(CHANGELOG))
    parser.add_argument("--title", action="store_true",
                        help="print the release's title (v<version> - short title) instead of its notes")
    parser.add_argument("--output", help="write here instead of standard output")
    args = parser.parse_args(argv)

    text = Path(args.changelog).read_text(encoding="utf-8")
    if args.title:
        body = release_title(text, args.version)
    else:
        try:
            body = notes(text, args.version)
        except ValueError as refused:
            print("release_notes: %s" % refused, file=sys.stderr)
            return 1
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as output:
            output.write(body + "\n")
    else:
        # The changelog contains em dashes and other punctuation a legacy console
        # codepage cannot represent, and printing it should not depend on which
        # locale the machine happens to use.
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
        sys.stdout.write(body + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
