#!/usr/bin/env bash
# Assemble the deployable site/ folder from two checkouts.
#
# The site duplicates nothing in git. Five canonical files live under site/
# (index.html, 404.html, llms.txt, robots.txt and this script); everything
# else it serves is copied in at deploy time from wherever that thing is
# canonical — which, since the website was split out of the skill, is two
# places:
#
#   this repository   previews/*.html, and the brand images under assets/
#   the skill repo    the template registry, the gallery thumbnails, the
#                     intake panel, and the MonoMind mark
#
# The skill repository is monomind-ai-lab/hi-ted-meet-lisa, checked out at
# $SKILL (default .skill/) — the deploy workflow does that with a second
# actions/checkout step, and locally you clone it yourself:
#
#   git clone --depth 1 https://github.com/monomind-ai-lab/hi-ted-meet-lisa .skill
#
# Reading the panel and the registry across the split is what keeps the
# website and the skill from drifting apart, which is the same reason they
# used to share one repository. It also means a missing or stale skill
# checkout would quietly produce a site with an empty gallery, so every
# skill-side input is checked before anything is copied and a missing one
# stops the build.
#
# Cloudflare Pages, were it building this directly, would run:
#
#   build command:     bash site/sync.sh
#   output directory:  site
#
# It does not — the Pages project is direct-upload and
# .github/workflows/deploy-pages.yml is the build. Run this locally before
# previewing site/index.html.
set -euo pipefail
cd "$(dirname "$0")/.."

# Every skill-repo path in this script goes through $SKILL, so a different
# checkout location is one edit (or one SKILL_DIR=... in the environment).
SKILL=${SKILL_DIR:-.skill}

die() { printf 'site/sync.sh: %s\n' "$*" >&2; exit 1; }

# Fail loudly and early. A half-assembled site is worse than no deploy: it
# deploys, it looks fine at a glance, and the gallery is empty.
if [ ! -d "$SKILL" ]; then
  die "no skill checkout at '$SKILL/'.
  The template registry, the gallery thumbnails, the intake panel and the
  MonoMind mark live in monomind-ai-lab/hi-ted-meet-lisa. Clone it beside
  this one, or point SKILL_DIR at an existing checkout:
    git clone --depth 1 https://github.com/monomind-ai-lab/hi-ted-meet-lisa $SKILL
    SKILL_DIR=/path/to/hi-ted-meet-lisa bash site/sync.sh"
fi

for f in templates/templates.json \
         assets/tedandlisa-intake.html \
         assets/monomind-mark-white.svg; do
  [ -f "$SKILL/$f" ] || die "missing '$SKILL/$f' — the skill checkout is
  incomplete or out of date. Update it and run this again."
done

# The thumbnails are a glob, so count them rather than name them: an empty
# thumbs/ directory is the exact failure this guard is here for.
if ! compgen -G "$SKILL/templates/thumbs/*.png" > /dev/null; then
  die "no gallery thumbnails at '$SKILL/templates/thumbs/*.png' — the skill
  checkout is incomplete, or the thumbnails have not been captured
  (python3 scripts/tedandlisa_thumbs.py in that repository)."
fi

# The local half, checked the same way for the same reason.
compgen -G "previews/*.html" > /dev/null || die "no previews/*.html in this repository"
for f in assets/tedlisaidea.jpg \
         assets/tedmeetslisa.jpg \
         assets/ted-and-lisa-in-frame.png \
         assets/tedlisa-cover-og.jpg; do
  [ -f "$f" ] || die "missing '$f' in this repository"
done

mkdir -p site/previews site/assets

# Live previews (the real generated files, local) + their gallery
# thumbnails (captured from the templates, so skill-side).
cp previews/*.html site/previews/
cp "$SKILL"/templates/thumbs/*.png site/previews/

# The intake panel — built to run from static hosting, falling back to a
# copy-answers payload when there is no runner. We inject the same
# window.__MONOMIND_INTAKE__ context the runner would (templates from the
# registry), with thumbnails as relative URLs instead of data URIs since
# the site serves the PNGs anyway. The canonical panel stays untouched.
SKILL="$SKILL" python3 - <<'PY'
import json, os, pathlib
root = pathlib.Path(".")
skill = pathlib.Path(os.environ["SKILL"])
entries = json.loads((skill / "templates/templates.json").read_text())["templates"]
cards = []
for t in entries:
    # This projection is a whitelist, so a registry field it does not name is
    # dropped on the way to the panel — silently, and visible only as a card
    # missing a line nobody remembers writing. `requires` is an install
    # precondition ("this needs X on the machine before it can run"), a
    # different claim from `dependencies` ("this file loads Y at runtime"),
    # and the one a reader needs first when deciding whether a template is
    # usable at all. No entry carries it yet, so the key is simply absent
    # from every card until the registry upstream ships it; nothing here has
    # to change on the day it does.
    card = {k: t.get(k) for k in
            ("id", "name", "tagline", "kind", "type", "layout", "best_for", "dependencies",
             "requires", "languages", "preview", "skill", "badge") if t.get(k) is not None}
    # `thumb` and `preview` are registry paths, relative to the skill repo.
    # Only their basenames survive: both land flat in site/previews/.
    thumb = skill / t.get("thumb", "")
    if t.get("thumb") and thumb.is_file():
        card["thumb"] = "previews/" + thumb.name
    if card.get("preview"):
        card["preview"] = "previews/" + pathlib.Path(card["preview"]).name
    cards.append(card)
html = (skill / "assets/tedandlisa-intake.html").read_text()
inject = ("<script>window.__MONOMIND_INTAKE__ = "
          + json.dumps({"mode": "web", "templates": cards}) + ";</script>\n")
marker = '<script>\n"use strict";'
assert marker in html, "intake panel script marker not found"
(root / "site/intake.html").write_text(
    html.replace(marker, inject + marker, 1))

# Every card the panel will render has to resolve to a file we just copied,
# or the gallery ships with holes in it.
missing = sorted({p for c in cards for p in (c.get("thumb"), c.get("preview"))
                  if p and not (root / "site" / p).is_file()})
assert not missing, "site/ is missing gallery files the panel references: " + ", ".join(missing)
print("site/intake.html written with", len(cards), "template cards")
PY

# Brand images referenced by the landing page.
cp assets/tedlisaidea.jpg assets/tedmeetslisa.jpg assets/ted-and-lisa-in-frame.png site/assets/
cp "$SKILL"/assets/monomind-mark-white.svg site/assets/

# The canonical mark uses currentColor, which an <img> renders black.
# Derive a solid-white copy for the page's dark chrome (deploy artifact
# only — the canonical file keeps currentColor).
sed 's/currentColor/#ffffff/g' "$SKILL"/assets/monomind-mark-white.svg \
  > site/assets/monomind-mark-solid-white.svg

# Favicon: the white mark on the brand's dark-olive tile, so it reads on
# light and dark tab strips alike. Derived, like the mark above.
SKILL="$SKILL" python3 - <<'PY'
import os, pathlib, re
mark = (pathlib.Path(os.environ["SKILL"]) / "assets/monomind-mark-white.svg").read_text()
mark = mark.replace("currentColor", "#ffffff")
inner = re.sub(r"^.*?<svg[^>]*>", "", mark, flags=re.S)
inner = inner.replace("</svg>", "")
fav = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
       '<rect width="512" height="512" rx="96" fill="#15160f"/>'
       '<g transform="translate(56 56) scale(0.78125)">' + inner + "</g></svg>")
pathlib.Path("site/assets/favicon.svg").write_text(fav)
print("site/assets/favicon.svg written")
PY

# Social/SEO meta image — page one of the Canva brand deck.
cp assets/tedlisa-cover-og.jpg site/assets/

# Cloudflare Web Analytics — cookieless, so no consent banner. Injected only
# when CF_BEACON_TOKEN is set: locally that means never, and the deploy
# workflow passes it from the CF_BEACON_TOKEN repository secret once it
# exists. A missing token skips silently — a placeholder token must never
# ship. The token itself is a one-time dashboard step: Cloudflare dashboard
# → Web Analytics → Add a site → html.monomind.one, then
#   gh secret set CF_BEACON_TOKEN
# The markup is Cloudflare's own snippet verbatim (type='module', which
# defers by default, wrapped in its comment markers) so a reader of the
# page source sees what it is.
# Note: index.html and 404.html are canonical files, so running this with
# the token set locally dirties the working tree — deploy-time use only.
# If you do run it locally, restore them:
#   git checkout site/index.html site/404.html
if [ -n "${CF_BEACON_TOKEN:-}" ]; then
  CF_BEACON_TOKEN="$CF_BEACON_TOKEN" python3 - <<'PY'
import os, pathlib
token = os.environ["CF_BEACON_TOKEN"]
beacon = ("<!-- Cloudflare Web Analytics -->"
          "<script type='module'"
          " src='https://static.cloudflareinsights.com/beacon.min.js'"
          " data-cf-beacon='{\"token\": \"" + token + "\"}'></script>"
          "<!-- End Cloudflare Web Analytics -->")
for name in ("index.html", "intake.html", "404.html"):
    p = pathlib.Path("site") / name
    html = p.read_text()
    if "cloudflareinsights.com/beacon.min.js" in html:
        print("site/" + name + ": beacon already present, left alone")
        continue
    assert "</body>" in html, name + " has no </body> to inject before"
    p.write_text(html.replace("</body>", beacon + "\n</body>", 1))
    print("site/" + name + ": analytics beacon injected")
PY
else
  echo "CF_BEACON_TOKEN not set — analytics beacon skipped"
fi

echo "site/ assembled:"
find site -type f | sort
