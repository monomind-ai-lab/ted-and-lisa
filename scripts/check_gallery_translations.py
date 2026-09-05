#!/usr/bin/env python3
"""Gate every gallery card on having its copy in the `T` translation table.

English, Korean and Traditional Chinese are first-class on this page: their
copy is written by hand and switched in place by `applyInline`, which walks
the `T` table near the bottom of site/index.html. Every entry is
`[selector, ko, zh-TW, all?]`, and without the flag it translates the *first*
element the selector matches -- `document.querySelector`, not `All`.

So a gallery card that nobody wrote entries for does not fail, does not warn
and does not look broken. It renders its English `kind` badge and its English
paragraph inside a page that is otherwise Korean or Chinese, in the one
section a reader scrolls to decide whether this is for them. Every card has
its entries today; this is the gate that keeps the next one from shipping
without them.

    python3 scripts/check_gallery_translations.py

It is the sibling of scripts/check_gallery.py and deliberately not a third
section of it. Two reasons, and the second is the load-bearing one:

  * They answer to different sources. That gate holds the gallery to
    templates/templates.json, which lives in the skill repository, so it
    cannot run at all without a checkout of it -- it exits 2 when .skill/ is
    absent. This one reads site/index.html and nothing else, so it runs in a
    bare clone, on a laptop, on a fork PR. Folding it in would make a check
    that needs nothing inherit a dependency it has no use for.
  * They fail about different things. "The gallery has drifted from the
    registry" and "this card ships English into a Korean page" are separate
    findings with separate fixes, and a reader of a red build should not have
    to work out which half of one gate went off.

What is shared is the parser: GalleryCards in check_gallery.py, imported
below rather than reimplemented, so the two gates cannot disagree about what
a card is. It records each card's element tree for this script's sake.

What is checked, reporting every gap rather than the first:

  1. Every card's `.kind` badge is translated -- by an entry that names it,
     or by one that names an element containing it. `.card.yours .meta h3`
     replaces the whole heading, kind span and all, so the bridge card is
     covered without a `.kind` entry of its own. Coverage through an
     ancestor is taken at its word: the entry replaces that subtree's
     innerHTML, so whether the replacement still says "yours" is the
     author's business, not something this script can read.
  2. Every `<p>` in every card's `.meta` is translated. Cards have one; the
     Slide Design card has two, its paragraph and its `.prov` line, and they
     are covered by two separate entries because a selector without the
     all-flag stops at the first match. That is modelled here rather than
     assumed: an entry covers only the first element it reaches in document
     order, so `.gallery .card:nth-child(7) .meta p` accounts for that
     card's paragraph and not for the `.prov` line below it.
  3. The reverse: a gallery-scoped entry that reaches no element at all.
     A card renamed, removed or renumbered leaves its entries behind,
     translating nothing -- the same hole seen from the other side.
  4. No gallery entry keys a card by position. `:nth-child` addresses
     whatever card is standing there at the time, so a card inserted above
     one hands it the next card's copy: every card still gets a string, just
     the wrong one, and nothing static can tell one Korean paragraph from
     another. That was checks 1 and 2's blind spot, and the reason they
     could only catch such a shift at its boundary -- the first card past
     the positional block, which loses its entry outright and is the one
     card in the run whose copy is *not* misplaced. Rejecting the shape
     removes the failure rather than reporting it late: an href key names
     one card and travels with it, and check_gallery.py already fails the
     build when two cards share an href, so the naming stays unique.

Entries carrying the all-flag are read but never counted as covering a
card's own copy. `.gallery .open` and `.gallery .layout[data-layout=...]`
are one string applied to every card that matches, which is right for a
shared label and wrong for card copy: counting them would let a card pass
with nothing of its own translated. If one of them is the only thing
reaching a slot, the failure says so.

Two things are deliberately not checked, so that the failures this prints
are all real:

  * Whether a translation is any good, or even in the right language. This
    gate knows that a string exists for a selector, not what it says.
  * Coverage of anything outside the gallery. The rest of the page's copy is
    static prose that changes when somebody rewrites a section, and a
    rewrite is reviewed. The gallery is the part that grows by appending,
    which is how a card arrives with no entries behind it.
  * Whether the right copy reached the right card. Two Korean paragraphs
    are both strings; nothing here reads them. This used to leave a real
    hole -- a card inserted above a positional entry moved the whole run
    onto the wrong cards, invisibly -- which is why check 4 above forbids
    the shape that made it possible rather than trying to detect it.

One limit worth stating, since it is a real gap rather than a choice: a
selector's first match is resolved within the gallery, because the gallery
is all this parser reads. An entry whose selector also matched something
earlier on the page would be diverted there, and this script would not see
it. No selector in `T` can do that today -- every gallery entry is scoped
under `.gallery` or `.card`, and no element outside the gallery carries
either class -- but a page-wide selector added later would be believed.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from check_gallery import PAGE, GalleryCards, label  # noqa: E402


# ── the `T` table ────────────────────────────────────────────────────
#
# Read out of the page's inline <script> as source text. The HTML parser
# cannot help here -- Python's HTMLParser hands back a script element's body
# as one opaque string, which is exactly right and exactly useless for this
# -- so the array literal is scanned directly. A scanner rather than a regex
# for the same reason the gallery gets a parser: the strings hold quotes,
# brackets and HTML of their own, and a pattern that mis-splits one entry
# fails by under-reporting, which is the one way this gate must not fail.

T_MARKER = "var T = ["


class TableError(Exception):
    """The `T` table is not shaped the way this script can read."""


def _string_at(src: str, i: int) -> int:
    """Index just past the JS string literal starting at src[i]."""
    quote, j, n = src[i], i + 1, len(src)
    while j < n:
        if src[j] == "\\":
            j += 2
            continue
        if src[j] == quote:
            return j + 1
        j += 1
    raise TableError(f"unterminated string literal at offset {i}")


def _skip(src: str, i: int) -> int:
    """Index of the next thing that is not whitespace, a comma or a comment."""
    n = len(src)
    while i < n:
        if src[i] in " \t\r\n,":
            i += 1
        elif src.startswith("/*", i):
            end = src.find("*/", i + 2)
            i = n if end < 0 else end + 2
        elif src.startswith("//", i):
            end = src.find("\n", i)
            i = n if end < 0 else end + 1
        else:
            return i
    return n


def _row(src: str, i: int) -> tuple[list[str], int]:
    """The top-level items of the array literal at src[i], and its end."""
    i += 1
    parts: list[str] = []
    buf: list[str] = []
    depth, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            end = _string_at(src, i)
            buf.append(src[i:end])
            i = end
        elif c in "[({":
            depth += 1
            buf.append(c)
            i += 1
        elif c in ")}":
            depth -= 1
            buf.append(c)
            i += 1
        elif c == "]" and depth == 0:
            parts.append("".join(buf).strip())
            return parts, i + 1
        elif c == "]":
            depth -= 1
            buf.append(c)
            i += 1
        elif c == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            i += 1
        else:
            buf.append(c)
            i += 1
    raise TableError("unterminated entry in the `T` table")


def unquote(item: str) -> str | None:
    """The value of a JS string literal, or None if that is not what it is."""
    if len(item) < 2 or item[0] not in "\"'" or item[-1] != item[0]:
        return None
    body = item[1:-1]
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1),
                                                                m.group(1)),
                  body)


def read_table(source: str) -> list[dict]:
    """Every `T` entry, as {selector, all, line}, in order."""
    start = source.find(T_MARKER)
    if start < 0:
        raise TableError(
            f"no `{T_MARKER}` in site/index.html — the inline translation "
            "table has been renamed or restructured")
    i = source.index("[", start)
    entries: list[dict] = []
    i += 1
    while True:
        i = _skip(source, i)
        if i >= len(source):
            raise TableError("unterminated `T` table")
        if source[i] == "]":
            return entries
        if source[i] != "[":
            raise TableError(
                f"unexpected {source[i:i + 24]!r} in the `T` table at "
                f"site/index.html:{source.count(chr(10), 0, i) + 1} — "
                "entries are expected to be [selector, ko, zh-TW, all?] "
                "array literals")
        line = source.count("\n", 0, i) + 1
        parts, i = _row(source, i)
        selector = unquote(parts[0]) if parts else None
        if selector is None:
            raise TableError(
                f"the `T` entry at site/index.html:{line} does not start "
                "with a quoted selector")
        flag = parts[3] if len(parts) > 3 else ""
        entries.append({
            "selector": selector,
            "all": flag not in ("", "0", "false", "null", "undefined"),
            "line": line,
        })


# ── selectors ────────────────────────────────────────────────────────
#
# Only the shapes `T` actually uses: descendant combinators over compounds
# of a tag name, classes, an id, attribute tests and :nth-child(N). Anything
# else raises, and a gallery-scoped selector that raises fails the run rather
# than being skipped -- a gate that quietly ignores what it cannot read is a
# gate that passes a card it never looked at.

TOKEN = re.compile(r"""
      \.(?P<cls>-?[A-Za-z_][-\w]*)
    | \#(?P<id>-?[A-Za-z_][-\w]*)
    | \[\s*(?P<attr>[-\w]+)\s*
      (?:=\s*(?P<q>["'])(?P<val>[^"']*)(?P=q)\s*)?\]
    | :nth-child\(\s*(?P<nth>\d+)\s*\)
""", re.X)
TAG = re.compile(r"[A-Za-z][A-Za-z0-9]*")

# A selector concerns the gallery when it names the container or a card.
# Tested on the raw text so that a selector this script cannot parse is
# still classified -- `.file-card` does not match, the leading dot is part
# of the pattern.
GALLERY_SCOPED = re.compile(r"\.(?:gallery|card)\b")


class SelectorError(ValueError):
    """A selector shape this script does not implement."""


def parse(selector: str) -> list[dict]:
    """A selector as a list of compounds, outermost first."""
    compounds = []
    for chunk in selector.split():
        if not chunk:
            continue
        comp = {"tag": None, "id": None, "classes": set(), "attrs": [],
                "nth": None}
        pos = 0
        m = TAG.match(chunk)
        if m:
            comp["tag"] = m.group(0).lower()
            pos = m.end()
        while pos < len(chunk):
            m = TOKEN.match(chunk, pos)
            if not m:
                raise SelectorError(
                    f"cannot read {chunk[pos:]!r} in {selector!r}")
            if m.group("cls"):
                comp["classes"].add(m.group("cls"))
            elif m.group("id"):
                comp["id"] = m.group("id")
            elif m.group("attr"):
                comp["attrs"].append((m.group("attr"), m.group("val")))
            else:
                comp["nth"] = int(m.group("nth"))
            pos = m.end()
        compounds.append(comp)
    if not compounds:
        raise SelectorError(f"empty selector {selector!r}")
    return compounds


def hits(comp: dict, el: dict, nth: int) -> bool:
    """Does one compound match this element, which is its parent's `nth`?"""
    if comp["tag"] and comp["tag"] != el["tag"]:
        return False
    if not comp["classes"] <= el["classes"]:
        return False
    if comp["id"] is not None and el["attrs"].get("id") != comp["id"]:
        return False
    for name, value in comp["attrs"]:
        if name not in el["attrs"]:
            return False
        if value is not None and el["attrs"][name] != value:
            return False
    return comp["nth"] is None or comp["nth"] == nth


def reaches(compounds: list[dict], chain: list[tuple[dict, int]]) -> bool:
    """Does the selector match the last element of this ancestor chain?

    `chain` is (element, nth-child) from the gallery down to the candidate.
    Descendant combinators only, so the leading compounds have to appear
    among the ancestors in order -- matched greedily from the nearest one
    outwards, which for a subsequence is exact, not an approximation.
    """
    el, nth = chain[-1]
    if not hits(compounds[-1], el, nth):
        return False
    want = len(compounds) - 2
    i = len(chain) - 2
    while want >= 0 and i >= 0:
        if hits(compounds[want], chain[i][0], chain[i][1]):
            want -= 1
        i -= 1
    return want < 0


def walk(gallery: dict, cards: list[dict]):
    """Every element of every card in document order, with its chain.

    Yields (card, element, chain). The chain starts at the gallery div,
    which is what the `.gallery ...` selectors are anchored on; a card's
    nth-child is its position, since the cards are the gallery's only
    element children.
    """
    for card in cards:
        root = card["tree"]
        if root is None:
            continue
        stack = [(root, card["position"], [(gallery, 1)])]
        while stack:
            el, nth, above = stack.pop(0)
            chain = above + [(el, nth)]
            yield card, el, chain
            stack = [(kid, n, chain)
                     for n, kid in enumerate(el["children"], 1)] + stack


# ── the cards' own copy ──────────────────────────────────────────────

def text_of(el: dict) -> str:
    """The element's text, its descendants' included, whitespace collapsed."""
    parts = [el["text"]] + [text_of(k) for k in el["children"]]
    return " ".join("".join(parts).split())


def descendants(el: dict):
    for kid in el["children"]:
        yield kid
        yield from descendants(kid)


def lineage(root: dict, target: dict) -> list[dict]:
    """`target` and its ancestors up to the card root, innermost first.

    An entry that matches an ancestor replaces that ancestor's innerHTML,
    and the target goes with it — so the whole chain is what has to be
    checked for coverage, not the element alone. Compared by identity: two
    elements of a card can hold equal values and still be different
    elements.
    """
    def find(el: dict, trail: list) -> list | None:
        trail = trail + [el]
        if el is target:
            return trail
        for kid in el["children"]:
            hit = find(kid, trail)
            if hit:
                return hit
        return None

    chain = find(root, [])
    return list(reversed(chain)) if chain else [target]


def slots(card: dict) -> list[dict]:
    """The elements of a card that carry its own copy, in document order.

    The `.kind` badge and every <p> inside `.meta` -- the two things written
    per card, and so the two things that go untranslated when a card is
    appended and the `T` table is not. Everything else in a card is either
    shared chrome with an all-flag entry of its own (`.open`, the layout
    mark) or has no words in it (the frame, the thumbnail).
    """
    root = card["tree"]
    if root is None:
        return []
    found = []
    for el in descendants(root):
        if "kind" in el["classes"]:
            found.append({"el": el, "what": "the `.kind` badge",
                          "sel": ".kind"})
    for el in descendants(root):
        if "meta" not in el["classes"]:
            continue
        for kid in descendants(el):
            if kid["tag"] != "p":
                continue
            own = sorted(kid["classes"])
            found.append({
                "el": kid,
                "what": (f"its <p class=\"{own[0]}\"> line" if own
                         else "its paragraph"),
                "sel": f".{own[0]}" if own else ".meta p",
            })
    return found


def suggest(card: dict, slot: dict) -> str:
    """The selector a maintainer should write for this slot.

    Keyed on the card's own href, which is the convention the table itself
    settled on: the seven positional entries only stay correct while nothing
    above them renumbers, and every card added since is keyed on its href so
    that it takes its translations with it. Uniformly so, including for the
    two cards whose existing entries are keyed on a class -- a class key is
    just as stable, but only some cards have one to use, and a rule with an
    exception in it is worse advice in a build failure than a rule.
    """
    return f'.gallery a[href="{card["href"]}"] {slot["sel"]}'


def suggest_href(entry: dict, cards: list[dict]) -> str:
    """The href form of a positional selector, when its card can be found.

    The entry still resolves today -- that is the whole trouble with it -- so
    the card it currently reaches is the card it means, and its href is the
    key it should have carried. If it reaches nothing, there is no card to
    name and the advice stays general.
    """
    if not entry["matches"]:
        return "`.gallery a[href=\"…\"] …`, naming the card it belongs to."
    card = entry["matches"][0][0]
    # Everything to the right of the compound that carried the position: that
    # part already names the slot inside the card and is kept verbatim. parse()
    # splits on whitespace, so the compounds line up with the raw chunks.
    chunks = entry["selector"].split()
    at = next(i for i, c in enumerate(entry["compounds"]) if c["nth"] is not None)
    tail = " ".join(chunks[at + 1:]) or "…"
    return f"['.gallery a[href=\"{card['href']}\"] {tail}', …] — "\
           f"{card['name'] or 'that card'}."


def main() -> int:
    argparse.ArgumentParser(
        description="Gate every card in site/index.html's gallery on having "
                    "its copy in the page's `T` translation table.",
    ).parse_args()

    if not PAGE.is_file():
        print(f"error: no landing page at '{PAGE}'", file=sys.stderr)
        return 2
    source = PAGE.read_text()

    parser = GalleryCards()
    parser.feed(source)
    if not parser.found_gallery:
        print('error: no <div class="gallery"> in site/index.html — has the '
              "landing page been restructured?", file=sys.stderr)
        return 2
    cards = parser.cards
    if not cards:
        print('error: <div class="gallery"> in site/index.html holds no '
              '<a class="card"> — has the markup been restructured?',
              file=sys.stderr)
        return 2

    try:
        table = read_table(source)
    except TableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # Parse every selector; a gallery-scoped one this script cannot read is
    # fatal, because "skipped it" and "it covers the card" are
    # indistinguishable from the outside.
    unreadable = []
    for entry in table:
        scoped = bool(GALLERY_SCOPED.search(entry["selector"]))
        entry["scoped"] = scoped
        try:
            entry["compounds"] = parse(entry["selector"])
        except SelectorError as exc:
            entry["compounds"] = None
            if scoped:
                unreadable.append(f"site/index.html:{entry['line']} "
                                  f"{entry['selector']!r} — {exc}")
    if unreadable:
        print("error: the `T` table has gallery selectors this gate cannot "
              "read, so it cannot say whether the cards are translated:",
              file=sys.stderr)
        for u in unreadable:
            print(f"  - {u}", file=sys.stderr)
        print("\n       Teach scripts/check_gallery_translations.py the "
              "shape, or key the entry\n       the way the cards around it "
              "are keyed.", file=sys.stderr)
        return 2

    # Every element of the gallery, in document order, so that an entry
    # without the all-flag can be resolved to the one element it reaches --
    # applyInline uses querySelector, not querySelectorAll.
    elements = list(walk(parser.gallery, cards))
    for entry in table:
        entry["matches"] = [
            (card, el) for card, el, chain in elements
            if entry["compounds"] and reaches(entry["compounds"], chain)]

    # element id -> the entries that translate it, all-flag ones apart.
    covers: dict[int, list[dict]] = {}
    shared: dict[int, list[dict]] = {}
    for entry in table:
        if not entry["matches"]:
            continue
        for card, el in (entry["matches"] if entry["all"]
                         else entry["matches"][:1]):
            (shared if entry["all"] else covers).setdefault(
                id(el), []).append(entry)

    problems: list[str] = []

    # ── cards → table ─────────────────────────────────────────────────
    for card in cards:
        for slot in slots(card):
            chain = lineage(card["tree"], slot["el"])
            if any(id(el) in covers for el in chain):
                continue
            note = ""
            if any(id(el) in shared for el in chain):
                only = shared[next(id(el) for el in chain
                                   if id(el) in shared)][0]
                note = (f" The all-elements entry {only['selector']!r} "
                        f"(site/index.html:{only['line']}) reaches it, but "
                        f"that is one string for every card it matches — it "
                        f"is a shared label, not this card's copy.")
            problems.append(
                f"{label(card)}: {slot['what']} "
                f"(\"{text_of(slot['el'])[:48]}\") has no entry in `T`, so it "
                f"stays English when the page is Korean or Chinese. Add "
                f"['{suggest(card, slot)}', '…', '…'] to the table near the "
                f"bottom of site/index.html.{note}")

    # ── table → cards ─────────────────────────────────────────────────
    for entry in table:
        if not entry["scoped"]:
            continue
        # A positional key addresses a slot in the gallery, not a card. It is
        # correct only until something above it renumbers, and the failure it
        # then causes is the one this gate cannot see -- so the shape is
        # refused outright rather than watched.
        positional = [c for c in (entry["compounds"] or [])
                      if c["nth"] is not None]
        if positional:
            nths = ", ".join(f":nth-child({c['nth']})" for c in positional)
            problems.append(
                f"the `T` entry at site/index.html:{entry['line']} keys "
                f"{entry['selector']!r} by position ({nths}). That addresses "
                f"whatever card is standing there, so a card inserted above "
                f"it hands this entry's copy to the wrong card — and every "
                f"card still gets a string, which is why nothing here could "
                f"catch it. Key it on the card's own href instead: "
                f"{suggest_href(entry, cards)}")
        if not entry["matches"]:
            problems.append(
                f"the `T` entry at site/index.html:{entry['line']} keys "
                f"{entry['selector']!r}, which reaches nothing in the "
                f"gallery. Its card was renamed, removed or renumbered and "
                f"the entry stayed — it translates nothing. Re-key it or "
                f"remove it.")

    if problems:
        print(f"error: site/index.html's gallery and its `T` table have "
              f"drifted — {len(problems)} "
              f"{'gap' if len(problems) == 1 else 'gaps'}:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("\n       Korean and Traditional Chinese are written by hand on "
              "this page, so a card\n       is translated only when somebody "
              "writes its entries. Key new ones on the\n       card's href, "
              "not on :nth-child — the positional entries are only correct\n"
              "       while nothing above them renumbers.", file=sys.stderr)
        return 1

    scoped = [e for e in table if e["scoped"]]
    covered = sum(len(slots(c)) for c in cards)
    print(f"every gallery card carries its copy in `T` "
          f"({len(cards)} cards, {len(scoped)} gallery entries)")
    print(f"  {covered} card-copy elements — every `.kind` and every "
          f"paragraph — reached by an entry of its own")
    for entry in scoped:
        if entry["all"]:
            n = len(entry["matches"])
            print(f"  {entry['selector']!r} is shared chrome, one string for "
                  f"all {n} element{'' if n == 1 else 's'} it matches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
