"""C3 sees a host written without a scheme too (v0.6.26, the third audit's T4), in every tree that ships (audit4 D4, E7).

docs/STANDARDS.md C3 says the shipped files name no unexpected host, and test_privacy_claims checks only hosts written
as URLs (`https://...`). Two comments named one bare - the lunar table's source (brand/days.py) and the squircle's
article (brand/shape.py) - and a third a documentation address (mcp/tools.py), which nothing connects to, but which the
sentence's letter forbids. Now a host written as a name is looked for as well, and only the hosts the product has a
reason to name stand: GitHub's, python.org's, ChatGPT's (pinned, handed to Codex), the Windows `chcp.com`, Microsoft's
manifest schemas and documentation, and, in the advanced edition's package, the courier's two.

What is read (`shipped_files`, the fourth audit's D4 and E7): the trees build/make_release.py puts in an archive, by its
own lists (APP_TREES, of assets only SHIPPED_ASSETS, ADVANCED_TREES, APP_SOURCES - `.mcp.json`'s source,
build/plugin-mcp.json - and the launcher's build/install/), every file of scripts/ as before, and the sources compiled
into what ships: the window's (gui/, advanced/gui/) and the setup program's (build/setup/). The URL test and the
api.github.com pin of test_privacy_claims read the same set. The human-facing documents an archive carries (README.md
and the docs APP_FILES names) are not read here: what they name - this repository, python.org, and the badges' pictures
on img.shields.io in the README - is what PRIVACY discloses or a picture a viewer of the README fetches, and whether C3
covers a document's pictures is the owner's word (audit4 E7).

How a host is known (D4): case-insensitively - `Telemetry.Example.COM` is a host - and by any ending in TLDS, every
country code and the generic endings, not nine. Code reads like a host there (`rect.top`, `self.app`, `System.IO`), so a
name is not taken for one when:
  - its ending is a file's extension the trees use (`watcher.py`, `Setup.cs`, `README.md`);
  - it is a key, or the start of a key, of either edition's English catalog (`page.chat.click`);
  - it ends outside the nine endings C3's first scan knew and its first label is a receiver in that same file: the
    start of another name there whose last label is no ending at all (`rect.left` makes `rect.top` code);
  - or it is one of CODE_NAMES, each read in its file and found to be code: a new one fails the test until it is checked
    the same way.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "tests"), str(ROOT / "build")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from test_privacy_claims import tracked  # noqa: E402

# Every country code (ISO 3166 and the delegated exceptions: ac, eu, su, uk) and the generic endings.
COUNTRY = frozenset("""
ac ad ae af ag ai al am ao aq ar as at au aw ax az ba bb bd be bf bg bh bi bj bm bn bo br bs bt bw by bz ca cc cd cf
cg ch ci ck cl cm cn co cr cu cv cw cx cy cz de dj dk dm do dz ec ee eg er es et eu fi fj fk fm fo fr ga gd ge gf gg
gh gi gl gm gn gp gq gr gs gt gu gw gy hk hm hn hr ht hu id ie il im in io iq ir is it je jm jo jp ke kg kh ki km kn
kp kr kw ky kz la lb lc li lk lr ls lt lu lv ly ma mc md me mg mh mk ml mm mn mo mp mq mr ms mt mu mv mw mx my mz na
nc ne nf ng ni nl no np nr nu nz om pa pe pf pg ph pk pl pm pn pr ps pt pw py qa re ro rs ru rw sa sb sc sd se sg sh
si sk sl sm sn so sr ss st su sv sx sy sz tc td tf tg th tj tk tl tm tn to tr tt tv tw tz ua ug uk us uy uz va vc ve
vg vi vn vu wf ws ye yt za zm zw""".split())
GENERIC = frozenset("""
com net org edu gov mil int arpa info biz name pro aero asia cat coop jobs mobi museum post tel travel xxx
app dev page new zip mov foo bar nexus phd prof esq day meme boo dad cloud online site website store shop tech space
live life world today news blog email link click top xyz club vip work works digital network systems solutions
services agency media studio design art photo photos pics pictures video music games game fun love cool social chat
support help mail inc llc ltd company business global center group zone one wiki fyi guru expert tips tools software
codes code hosting host domains download win run bot bio eco google amazon microsoft apple android chrome youtube play
search office azure windows bing xbox skype goog gmail academy africa amsterdam berlin london paris tokyo nyc moscow
kim lol wtf fail sucks porn sex adult casino bet poker money cash pay finance financial bank insure credit loans tax
capital fund trade market markets exchange health care clinic dental doctor fit fitness bike golf ski surf red blue
green black pink gold silver plus computer data security safe secure analytics science technology institute
university school education events consulting marketing management partners ventures holdings enterprises
international city country land house home homes estate properties realty rent rentals build builders construction
legal law lawyer attorney accountant gives charity foundation church review reviews forum community team family kids
baby style fashion clothing shoes jewelry beauty hair tours flights hotel hotels vacations cruise camera audio tv radio
film movie theater show pizza cafe restaurant pub beer wine coffee kitchen recipes food farm garden auto car cars
motorcycles taxi parts repair tires lat lgbt ninja rocks town cab express direct deals sale discount coupons gift gifts
cards report reports contact icu monster quest""".split())
TLDS = COUNTRY | GENERIC
# The endings C3's first scan knew (v0.6.26 T4): a name under one of them is never let off as a receiver's member.
FIRST_NINE = frozenset(("com", "org", "net", "kr", "gov", "hk", "edu", "io", "ai"))
# A file's extension the shipped trees name files by, where it is a country code or an ending as well.
EXTENSIONS = frozenset(("py", "cs", "md", "sh", "js", "ps", "zip", "exe", "json", "txt", "in", "so", "cc", "pl",
                        "ts", "cat"))
BARE_HOST = re.compile(r"(?<![\w.@-])((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+([a-z]{2,63}))(?![\w(-])", re.I)
CHAIN = re.compile(r"(?<![\w.])[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+")
# Names the scan reads as hosts that are code, each read in its file (2026-11-23): a member of an object, a module or a
# type (`os.name`, `Keys.Space`, `DockStyle.Top`, `System.IO`), or an M-record's name (`measurement.MK`).
CODE_NAMES = frozenset("""
args.home arguments.home authfile.name autoresult.fail brand.design build.page chevron.to chooser.id copied.id
credit.family dayart.fit definition.id dockstyle.top e.data each.id ended.code entry.name error.code exc.code gone.code
helpnode.id keys.space made.host made.name marketplace.name mcpserverstatus.tools measurement.mk measurement.mq
measurement.mr measurement.ms measurement.mu os.name outcomechart.bar ownprocess.id p.parts path.name paths.home
pwsh.run refused.code reporter.windows righttoleft.no search.click self.code self.home self.id semibold.name
softmenurenderer.fit started.id style.name system.io threads.name""".split())
ALLOWED = re.compile(r"^(?:(?:api|raw|objects|release-assets)\.)?github(?:usercontent)?\.com$|^(?:www\.)?python\.org$"
                     r"|^chatgpt\.com$|^chcp\.com$|^agent-plugins\.org$|^(?:schemas|docs|learn)\.microsoft\.com$")
COURIER_ONLY = re.compile(r"^(?:api\.telegram\.org|status\.openai\.com)$")
ADVANCED = "advanced/src/"
# Of the shipped trees, besides make_release's: every file of scripts/ (read whole, as before), the launcher's, the
# window's sources and the setup program's, which are compiled into what ships.
COMPILED_OR_READ = ("scripts", "build/install", "gui", "advanced/gui", "build/setup", "advanced/src", "advanced/skills")


def shipped_files() -> list:
    """Every tracked file of a tree that ships or is compiled into what ships (the module's docstring), once each."""
    import make_release
    patterns = []
    for tree in make_release.APP_TREES:
        listed = make_release.LISTED_TREES.get(tree)
        if listed is None or tree == "scripts":
            patterns.append(tree + "/*")
        else:
            patterns.extend("%s/%s" % (tree, name) for name in listed)
    patterns.extend(source + "/*" for source, _placed in make_release.ADVANCED_TREES)
    patterns.extend(make_release.APP_SOURCES.values())
    patterns.extend(tree + "/*" for tree in COMPILED_OR_READ)
    found, seen = [], set()
    for pattern in patterns:
        for path in tracked(pattern):
            if path not in seen:
                seen.add(path)
                found.append(path)
    return found


def catalog_keys() -> frozenset:
    keys = set()
    for catalog in ("src/codex_auto_resume/locales/en.json", "advanced/src/codex_auto_resume_advanced/locales/en.json"):
        keys.update(key.lower() for key in json.loads((ROOT / catalog).read_text(encoding="utf-8")))
    return frozenset(keys)


def hosts_in(text: str, keys=frozenset()) -> list:
    """The names in `text` read as hosts, lower-cased, by the rules of the module's docstring but CODE_NAMES."""
    # A receiver: the first label of a chain whose last label is no ending (`rect.left`), each with the chains that made
    # it one, so a host's own labels never make its first one a receiver.
    receivers = {}
    for chain in CHAIN.findall(text):
        last = chain.rsplit(".", 1)[1]
        if last.lower() not in TLDS or not last.isalpha():
            receivers.setdefault(chain.split(".", 1)[0].lower(), set()).add(chain.lower())
    found = set()
    for match in BARE_HOST.finditer(text):
        name, ending = match.group(1).lower(), match.group(2).lower()
        if ending not in TLDS or ending in EXTENSIONS:
            continue
        if name in keys or any(key.startswith(name + ".") for key in keys):
            continue
        if ending not in FIRST_NINE and receivers.get(name.split(".")[0], set()) - {name}:
            continue
        found.add(name)
    return sorted(found)


def bare_hosts():
    found = []
    keys = catalog_keys()
    for path in shipped_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        name = str(path.relative_to(ROOT)).replace("\\", "/")
        for host in hosts_in(text, keys):
            if host in CODE_NAMES or ALLOWED.match(host) or (name.startswith(ADVANCED) and COURIER_ONLY.match(host)):
                continue
            found.append("%s: %s" % (name, host))
    return sorted(found)


class BareHostTests(unittest.TestCase):
    def test_no_shipped_file_names_a_host_the_product_has_no_reason_to(self):
        self.assertEqual(bare_hosts(), [], "a shipped file names a host without a scheme that we do not expect "
                                           "(a name that is code goes into CODE_NAMES once it is read in its file)")

    def test_the_lookup_sees_what_it_is_for(self):
        for sample, expected in (("the Institute, astro.kasi.re.kr) computes", ["astro.kasi.re.kr"]),
                                 ("(figma.com/blog)", ["figma.com"]), ("args.left args.dev self.x self.app.logger.info", []),
                                 # D4: what the nine lowercase endings missed.
                                 ('Url = "https://telemetry.example.dev/x";', ["telemetry.example.dev"]),
                                 ('Url = "https://Telemetry.Example.COM/x";', ["telemetry.example.com"]),
                                 ("beacon.tracker.app and stats.example.co", ["beacon.tracker.app", "stats.example.co"]),
                                 ("watcher.py Setup.cs README.md", [])):
            found = [host for host in hosts_in(sample) if host not in CODE_NAMES]
            self.assertEqual(found, expected, sample)
        self.assertEqual(hosts_in("rect.left + rect.top"), [], "a receiver's member is code")
        self.assertEqual(hosts_in("rect.left; evil.example.com"), ["evil.example.com"])
        self.assertEqual(hosts_in("example.left; example.com"), ["example.com"], "never let off under the first nine")
        self.assertEqual(hosts_in("page.chat.click", frozenset({"page.chat.click.page"})), [], "a catalog key's start")
        self.assertIsNone(ALLOWED.match("figma.com"))
        self.assertIsNone(ALLOWED.match("github.com.example.org"))
        self.assertIsNotNone(ALLOWED.match("raw.githubusercontent.com"))

    def test_every_tree_that_ships_is_read(self):
        read = {str(path.relative_to(ROOT)).replace("\\", "/") for path in shipped_files()}
        for wanted in ("gui/SoftTheme.cs", "advanced/gui/AdvancedPage.cs", ".codex-plugin/plugin.json",
                       ".agents/plugins/marketplace.json", "build/plugin-mcp.json", "build/setup/Setup.cs",
                       "build/install/install.ps1", "scripts/bootstrap.ps1", "src/codex_auto_resume/brand/days.py"):
            self.assertIn(wanted, read)
        self.assertTrue(any(name.startswith("skills/") for name in read))
        self.assertTrue(any(name.startswith("advanced/skills/") for name in read))
        self.assertTrue(any(name.startswith("advanced/src/") for name in read))

    def test_every_code_name_is_still_somewhere(self):
        # An entry nothing names any more is taken out, so the list stays what the shipped files hold.
        keys, named = catalog_keys(), set()
        for path in shipped_files():
            try:
                named.update(hosts_in(path.read_text(encoding="utf-8"), keys))
            except (UnicodeDecodeError, OSError):
                continue
        self.assertEqual(sorted(CODE_NAMES - named), [])


if __name__ == "__main__":
    unittest.main()
