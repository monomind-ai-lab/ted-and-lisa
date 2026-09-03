# Ted and Lisa — the website

<p align="left">
  <img src="assets/tedlisaidea.jpg" alt="Hi Ted, Meet Lisa — ideas that come to life in HTML" style="width: 100%; max-width: 100%;">
</p>

> **The source of [html.monomind.one](https://html.monomind.one) — the public
> front door for [Hi Ted, Meet Lisa](https://github.com/monomind-ai-lab/hi-ted-meet-lisa).**

This repository is the website, not the skill. It holds the landing page, the
live template previews, the brand images, two Cloudflare Pages Functions and
the deploy workflow. The skill those pages are about — the templates, the
intake panel, the registry, the scripts — lives in
[monomind-ai-lab/hi-ted-meet-lisa](https://github.com/monomind-ai-lab/hi-ted-meet-lisa),
and this repository reads from it at build time rather than copying it.

If you came here to *use* Lisa — install the plugin, build a deck, add a
template — you want the skill repository. Its README has all of that. Nothing
here is a second copy of it.


---

## ✅ What is where

**In this repository**

- `site/` — six tracked files: `index.html`, `lisa-ppt.html`, `404.html`,
  `llms.txt`, `robots.txt`, and `sync.sh`. Everything else under `site/` is
  assembled and gitignored.
- `previews/*.html` — the live previews, one per registry template. Real
  generated files, not screenshots: open one and it behaves like the deck it
  came from. The gallery links to every one, and a gate makes sure of it.
- `assets/` — the brand images the landing page uses: the hero, the framed
  figure, and the social/SEO cover.
- `functions/` — two Cloudflare Pages Functions, `e.js` and `SKILL.md.js`.
- `scripts/check_gallery.py` — the gate that holds the landing page's gallery
  to the template registry, and `scripts/check_gallery_translations.py`, the
  gate that holds each of its cards to the page's translation table. See
  *Two galleries, two mechanics* below.
- `.github/workflows/deploy-pages.yml` — the deploy.

**In the skill repository, read at build time**

- `templates/templates.json` — the registry. The intake panel is built from
  it; the landing page's gallery is held to it by a gate.
- `templates/thumbs/*.png` — the gallery thumbnails.
- `assets/tedandlisa-intake.html` — the intake panel served at `/intake.html`.
- `assets/monomind-mark-white.svg` — the MonoMind mark, which also becomes the
  page's solid-white variant and the favicon.

Splitting the site out of the skill was a packaging decision, not a decision to
keep two copies of the gallery. The registry, the panel and the thumbnails stay
canonical where the skill is, and the build reaches across for them.


### Two galleries, two mechanics

**Read this before adding a template.** This site shows the templates twice,
and the two galleries are built differently:

- **The intake panel** at `/intake.html` is **generated**. `site/sync.sh` builds
  its card list from `templates/templates.json` at build time, so a template
  added to the skill appears there with nothing here to update.
- **The gallery on the landing page** is **hand-written**. Its cards are prose
  in `site/index.html`, with copy written for a reader of this page and
  translated into Korean and Traditional Chinese in the `T` table at the bottom
  of the same file. So a new template does **not** appear on the landing page by
  itself. Somebody has to write the card.

That is deliberate, not a gap waiting to be closed: the card copy is editorial
and better than the registry's taglines — the registry says "Horizontal
presentation deck, dark ink and accent halos" where the card says "The
presentation deck. Horizontal slides, deck menu, keyboard and touch navigation,
EN → KR / ZH translation on demand." Generating the gallery from the registry
would overwrite hand-tuned copy in three languages with blander text.

What was a gap is that nothing checked. `motion-website` sat in the registry for
a whole release wave with no card on the landing page: its preview was generated,
copied and served, and reachable only by typing the URL. So the gallery is
hand-written **but gated**. `scripts/check_gallery.py` fails the build when the
registry and the gallery disagree — a registry template with no card, a card
whose preview or thumbnail does not resolve, a card pointing at a template that
no longer exists — and it names every discrepancy by template id:

```sh
python3 scripts/check_gallery.py     # registry at .skill/, or $SKILL_DIR
```

It runs in the PR check and in the deploy, before the assembly, so an
incomplete gallery cannot ship. The two cards with no template behind them —
the "Your Template" bridge card and Lisa's PPT, which is a separate product
this site builds nothing for — are named in the script with the reason, so the
gate stays narrow. One consequence worth knowing: because the check reads the
skill repository's `main`, a template merged there turns every subsequent PR
here red until its card is written. That is the pressure working, not a fault.

**Writing the card is half of it.** The card copy is also translated by hand:
Korean and Traditional Chinese live in the `T` table near the bottom of
`site/index.html`, and `applyInline` swaps them in place. A card with no
entries there does not fail and does not look broken — it renders its English
badge and its English paragraph inside a page that is otherwise Korean, in the
one section a reader scrolls to decide whether this is for them. So there is a
second gate beside the first:

```sh
python3 scripts/check_gallery_translations.py    # needs nothing but site/
```

It checks every card's `kind` badge and every paragraph in its `meta`, names
the cards nothing translates, and prints the entry to add. It also catches the
reverse — an entry whose card was renamed or renumbered out from under it, so
that it now translates nothing.

When you write the entries, **key them on the card's `href`**, like this:

```js
['.gallery a[href="previews/your-template.html"] .kind', '…', '…'],
['.gallery a[href="previews/your-template.html"] .meta p', '…', '…'],
```

The seven oldest entries are keyed on `.gallery .card:nth-child(N)` instead,
and those are only correct while nothing above them renumbers — insert a card
at the top and each one quietly slides onto the wrong card. An entry keyed on
its href takes its translations with it wherever the card ends up. The gate
catches the boundary of a renumber, where the shift runs off the end of the
positional block; it cannot tell one Korean paragraph from another, so it
cannot catch the middle of one. Both limits are written down at the top of the
script.


---

## ✅ The build

`site/sync.sh` assembles the deployable folder. It needs a checkout of the
skill repository, which it looks for at `.skill/` (override with `SKILL_DIR`):

```sh
git clone --depth 1 https://github.com/monomind-ai-lab/hi-ted-meet-lisa .skill
bash site/sync.sh
open site/index.html
```

`.skill/` is gitignored. If it is missing, or any file the script needs from it
is absent, the script says which one and exits non-zero — a silent partial
build would deploy a page whose gallery is empty and whose intake panel is
missing, and it would look fine from the outside.

What it produces, all gitignored: `site/previews/` (the previews and the
gallery thumbnails), `site/intake.html` (the panel, with the template list injected as
the runner would inject it), and `site/assets/` (the brand images, the mark, the
solid-white mark, and a favicon derived from it).

The deploy is `.github/workflows/deploy-pages.yml`, on every push to `main`. It
checks out both repositories, runs three gates, then `site/sync.sh`, then
`wrangler pages deploy site` from the repository root. Two of them are one per
gallery: the skill repository's `scripts/tedandlisa_intake_fallback.py --check`
(the intake panel carries a generated fallback template list for `file://` use,
and a drifted one would ship a gallery missing a template) and this
repository's `scripts/check_gallery.py` (the landing page's gallery is
hand-written, and a missing card would ship a template with no way to reach it).
The third is this repository's `scripts/check_gallery_translations.py` (the
card copy is hand-written in three languages, and a card with no entries ships
English into a Korean page). It reads `site/index.html` alone, needing neither
checkout's registry, so it runs first. Any one of the three stops the deploy.

The root matters. Wrangler compiles `functions/` from the current working
directory, so deploying `site` *from the root* is what carries the functions up
with the static files. Run it from inside `site/` and the page deploys without
them.

Two secrets, both documented at the top of the workflow file:
`CLOUDFLARE_API_TOKEN` (required) and `CF_BEACON_TOKEN` (optional — while it is
unset, `sync.sh` skips the analytics beacon rather than shipping a placeholder).


---

## ✅ The two functions

**`/e`** — the five funnel events, counted and nothing more. Cloudflare Web
Analytics gives the site pageviews and referrers but has no custom events; this
takes an event name from a five-item allow-list and ignores everything else
about the request. No ip, no user agent, no id, no cookie. It answers 204
always, and records nothing at all until someone binds a Workers Analytics
Engine dataset to it.

**`/SKILL.md`** — a proxy, not a file. `https://html.monomind.one/SKILL.md` is
the URL `llms.txt` advertises to agents: point anything that can read a URL at
it and it has the whole procedure. The document itself is canonical at
`skills/lisa/SKILL.md` in the skill repository, so this route fetches it per
request and caches it at the edge for a few minutes. A copy committed here
would be a second original, and it would go stale the first time the skill
changed and nobody noticed — an agent following the advertised URL would then
build against instructions the skill no longer gives. On an upstream failure
the route answers 502 with a plain-text explanation, never a blank 200.


---

## ✅ License

[MIT + Commons Clause](LICENSE), the same as the skill.

Use it freely, including commercially — build with it, ship what you make with
it. The one thing the Commons Clause withholds is selling the components
themselves: not alone, not bundled, not as a port.

See [NOTICE](NOTICE) for what this distribution bundles.
