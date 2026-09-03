#!/usr/bin/env python3
"""Gate the landing-page gallery against the skill's template registry.

This site has two galleries, and they are built by different mechanics:

  the intake panel   site/intake.html is generated at build time by
                     site/sync.sh from templates/templates.json, so a
                     template added to the skill appears there by itself.
  the landing page   the gallery in site/index.html is hand-written prose.
                     Its cards are editorial: the copy is written for a
                     reader of this page, in three languages, and it is
                     deliberately better than the registry's taglines.
                     Compare monomind-deck, where the card says "The
                     presentation deck. Horizontal slides, deck menu,
                     keyboard and touch navigation, EN -> KR / ZH
                     translation on demand" and the registry says
                     "Horizontal presentation deck, dark ink and accent
                     halos."

Because the second one only gains a card when a human writes one, a
template can land in the registry, appear in the panel, have its preview
generated and served -- and have no card. That is not hypothetical:
motion-website sat like that for a whole release wave, its live preview
reachable only by typing the URL.

Generating the gallery from the registry would fix the drift and lose the
copy, in three languages. So this is a gate instead of a generator: the
cards stay hand-written, and the drift cannot ship silently. It is the same
answer, and deliberately the same shape, as the skill repository's
scripts/tedandlisa_intake_fallback.py --check, which exists for exactly
this class of bug on the panel side.

    python3 scripts/check_gallery.py                    # registry at .skill/
    SKILL_DIR=/path/to/hi-ted-meet-lisa python3 scripts/check_gallery.py
    python3 scripts/check_gallery.py --skill /path/to/hi-ted-meet-lisa

What it checks, reporting every discrepancy rather than the first:

  1. Every registry template has a gallery card. A card is matched to a
     template by its href: sync.sh copies previews flat into
     site/previews/, so the card's href is "previews/" plus the basename
     of the registry's `preview`.
  2. Every card's targets resolve -- the preview HTML here in previews/,
     and the thumbnail in the skill checkout's templates/thumbs/. Both are
     checked where they are canonical rather than in the assembled site/,
     so a failure names the file to fix and does not depend on having run
     sync.sh first.
  3. The reverse: no card links a preview no registry template claims, and
     no two cards claim the same one. A template renamed or dropped
     upstream leaves a card pointing at a preview that will stop being
     copied, which is the same hole seen from the other side.

Exceptions are named, not inferred, because a gate with a category-shaped
hole in it is a rubber stamp:

  * A card whose href is not a preview at all must be listed in
    EDITORIAL_CARDS below with the reason it has no template behind it.
    There are two, and both are prose by design. An href that is not
    listed fails -- and so does a listing whose card is gone, so the table
    cannot quietly fill up with permissions nobody needs.
  * A registry entry with no `preview` cannot be matched to a card and so
    cannot be required to have one. Only a `kind: external` handoff may
    lack one: that entry is not a template of this skill, it is a pointer
    at another one, and the site builds nothing for it. This mirrors how
    the skill's own checks treat the kind -- scripts/check_overflow.py
    skips `kind: external` when it collects first-party template files,
    and the panel simply renders no preview link for an entry without a
    `preview`. A first-party template with no `preview` fails here, loudly,
    rather than being excused. (slide-design is the one external entry
    today, and it does carry a preview, so it is checked like every other
    card.)

Deliberately not checked, so that the failures this prints are all real:

  * A preview file in previews/ that no registry template claims. The
    previews are canonical here and the registry is canonical in the skill
    repository, so a preview legitimately lands before the entry that
    names it. Failing on that would fail the honest half of a two-repo
    change.
  * Translation coverage. Each card also needs entries in the `T` table at
    the bottom of index.html or it stays English in Korean and Chinese.
    Every card has them today. Gating it means matching `T`'s selectors --
    some positional, some by href, some by class -- against the cards, and
    that is a second gate, not a clause of this one.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "site" / "index.html"
PREVIEWS = ROOT / "previews"

# Cards with no registry template behind them, by exact href, each with the
# reason it is prose. Narrow on purpose: an unlisted non-preview card fails,
# and so does a listing whose card has gone.
EDITORIAL_CARDS = {
    "#for-teams":
        "the bridge card -- \"Your Template\", an empty frame inviting the "
        "reader to bring their own look. It jumps to the for-teams section; "
        "there is no template behind it and never will be.",
    "lisa-ppt":
        "Lisa's PPT -- a separate, affiliated PowerPoint product, installed "
        "on its own. It has no registry entry any more, this site builds and "
        "hosts nothing for it, so there is no preview to link; the card "
        "points at this site's own page for it.",
}

# Tags that never nest, so they must not move the depth counter.
VOID = {"img", "br", "hr", "input", "meta", "link", "source", "area",
        "base", "col", "embed", "param", "track", "wbr"}


class GalleryCards(HTMLParser):
    """The <a class="card"> children of <div class="gallery">, in order.

    A real parser rather than a regex: the page carries inline <script> with
    angle brackets in strings and long HTML comments between the cards, and
    both of those confuse pattern matching in ways that would show up as a
    card silently not counted -- which is the failure this gate exists to
    catch, so it must not be able to cause it.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[dict] = []
        self.found_gallery = False
        self._in_gallery = False
        self._depth = 0
        self._card: dict | None = None
        self._card_depth = 0
        self._in_h3 = False
        self._in_kind = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = dict(attrs)
        cls = set((a.get("class") or "").split())
        if not self._in_gallery:
            if tag == "div" and "gallery" in cls:
                self._in_gallery = True
                self.found_gallery = True
                self._depth = 1  # we are now inside the gallery div
            return
        if tag == "a" and "card" in cls and self._card is None:
            self._card = {
                "position": len(self.cards) + 1,
                "href": a.get("href", ""),
                "classes": sorted(cls - {"card"}),
                "img": None,
                "noshot": False,
                "name": "",
                "line": self.getpos()[0],
            }
            self._card_depth = self._depth
        if self._card is not None:
            if tag == "img" and self._card["img"] is None:
                self._card["img"] = a.get("src", "")
            elif tag == "h3":
                self._in_h3 = True
            elif tag == "span":
                if "noshot" in cls:
                    self._card["noshot"] = True
                if self._in_h3 and "kind" in cls:
                    self._in_kind = True
        if tag not in VOID:
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if not self._in_gallery or tag in VOID:
            return
        self._depth -= 1
        if tag == "h3":
            self._in_h3 = False
        elif tag == "span":
            self._in_kind = False
        if self._card is not None and tag == "a" and self._depth == self._card_depth:
            self._card["name"] = " ".join(self._card["name"].split())
            self.cards.append(self._card)
            self._card = None
        if self._depth == 0:
            self._in_gallery = False

    def handle_data(self, data: str) -> None:
        if self._card is not None and self._in_h3 and not self._in_kind:
            self._card["name"] += data


def label(card: dict) -> str:
    """A card named the way a person would look for it in the file."""
    name = card["name"] or "(unnamed)"
    return f"card {card['position']} \"{name}\" (site/index.html:{card['line']})"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Gate site/index.html's gallery against the skill's "
                    "template registry.")
    ap.add_argument("--skill", default=os.environ.get("SKILL_DIR", ".skill"),
                    help="the hi-ted-meet-lisa checkout holding "
                         "templates/templates.json (default: $SKILL_DIR, "
                         "else .skill)")
    args = ap.parse_args()

    skill = pathlib.Path(args.skill)
    if not skill.is_absolute():
        skill = ROOT / skill
    registry = skill / "templates" / "templates.json"
    if not registry.is_file():
        print(f"error: no template registry at '{registry}'.\n"
              "       The registry lives in monomind-ai-lab/hi-ted-meet-lisa. "
              "Clone it beside\n"
              "       this repository as .skill/, or point --skill / SKILL_DIR "
              "at a checkout.",
              file=sys.stderr)
        return 2
    if not PAGE.is_file():
        print(f"error: no landing page at '{PAGE}'", file=sys.stderr)
        return 2

    entries = json.loads(registry.read_text())["templates"]

    parser = GalleryCards()
    parser.feed(PAGE.read_text())
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

    problems: list[str] = []
    notes: list[str] = []

    # A card is matched to a template by href, so a duplicated href would
    # make one template's card answer for another's. Group rather than
    # overwrite, and say so.
    by_href: dict[str, list[dict]] = {}
    for card in cards:
        by_href.setdefault(card["href"], []).append(card)
    for href, group in by_href.items():
        if len(group) > 1:
            problems.append(
                f"{len(group)} gallery cards link the same href '{href}': "
                + ", ".join(label(c) for c in group))

    # ── registry → gallery ────────────────────────────────────────────
    claimed: dict[str, str] = {}   # href -> template id
    for t in entries:
        tid = t.get("id") or "(entry with no id)"
        preview = t.get("preview")
        if not preview:
            if t.get("kind") == "external":
                notes.append(f"{tid}: kind:external with no `preview` — a "
                             "handoff to another skill, so this site previews "
                             "nothing for it and needs no card")
            else:
                problems.append(
                    f"{tid}: no `preview` in the registry. Only a "
                    "`kind: external` handoff may lack one; a template of "
                    "this skill needs a preview here and a card that links it.")
            continue
        href = "previews/" + pathlib.PurePosixPath(preview).name
        claimed[href] = tid
        group = by_href.get(href) or []
        if not group:
            problems.append(
                f"{tid}: no gallery card in site/index.html links '{href}'. "
                f"The registry has the template and sync.sh will serve its "
                f"preview, so the live page would offer no way to reach it. "
                f"Write a card in <div class=\"gallery\"> (and its `T` entries "
                f"below, keyed on the href rather than a position).")
            continue
        card = group[0]
        target = PREVIEWS / pathlib.PurePosixPath(preview).name
        if not target.is_file():
            problems.append(
                f"{tid}: {label(card)} links '{href}', but "
                f"'{target.relative_to(ROOT)}' does not exist in this "
                f"repository — the card would open a 404.")
        thumb = t.get("thumb")
        if thumb:
            # sync.sh copies the skill's thumbs flat into site/previews/, so
            # that is the src the card must carry.
            want_img = "previews/" + pathlib.PurePosixPath(thumb).name
            if card["img"] != want_img:
                problems.append(
                    f"{tid}: {label(card)} shows "
                    f"'{card['img'] or 'no <img>'}' where the registry's "
                    f"`thumb` says '{want_img}'.")
            elif not (skill / thumb).is_file():
                problems.append(
                    f"{tid}: {label(card)} shows '{want_img}', but the "
                    f"registry's thumbnail '{thumb}' is not in the skill "
                    f"checkout — capture it (python3 "
                    f"scripts/tedandlisa_thumbs.py there) or the card renders "
                    f"a broken image.")
        elif card["img"]:
            problems.append(
                f"{tid}: {label(card)} shows '{card['img']}', but the "
                f"registry entry has no `thumb` — nothing will copy that file "
                f"into site/previews/.")

    # ── gallery → registry ────────────────────────────────────────────
    for card in cards:
        href = card["href"]
        if href.startswith("previews/"):
            if href not in claimed:
                problems.append(
                    f"{label(card)} links '{href}', which no template in "
                    f"templates/templates.json claims. The template was "
                    f"renamed or dropped upstream and sync.sh will stop "
                    f"copying that preview — fix the href or remove the card.")
        elif href not in EDITORIAL_CARDS:
            problems.append(
                f"{label(card)} links '{href}', which is not a preview and "
                f"which no registry template backs. If the card is deliberate "
                f"prose, add its href to EDITORIAL_CARDS in "
                f"scripts/check_gallery.py with the reason; otherwise point it "
                f"at a preview.")

    # An exception whose card has gone is a permission nobody needs. Failing
    # on it is what keeps the table above from becoming a rubber stamp.
    for href in EDITORIAL_CARDS:
        if href not in by_href:
            problems.append(
                f"EDITORIAL_CARDS in scripts/check_gallery.py excuses a "
                f"gallery card linking '{href}', but the gallery has no such "
                f"card. Remove the entry.")

    if problems:
        print(f"error: site/index.html's gallery has drifted from the "
              f"template registry — {len(problems)} "
              f"{'discrepancy' if len(problems) == 1 else 'discrepancies'}:",
              file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("\n       The gallery is hand-written on purpose: its card copy "
              "is editorial and\n"
              "       lives in three languages. Fix the cards, not this "
              "script.", file=sys.stderr)
        return 1

    editorial = [c["href"] for c in cards if not c["href"].startswith("previews/")]
    print(f"gallery is in step with the registry "
          f"({len(claimed)} previewable templates, {len(cards)} cards)")
    print(f"  every registry template has a card, and every card's preview "
          f"and thumbnail resolve")
    if editorial:
        print(f"  {len(editorial)} editorial "
              f"{'card' if len(editorial) == 1 else 'cards'} with no registry "
              f"entry, by design: " + ", ".join(editorial))
    for note in notes:
        print(f"  {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
