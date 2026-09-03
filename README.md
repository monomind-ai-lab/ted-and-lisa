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

- `site/` — five tracked files: `index.html`, `404.html`, `llms.txt`,
  `robots.txt`, and `sync.sh`. Everything else under `site/` is assembled and
  gitignored.
- `previews/*.html` — the live previews, one per registry template. Real
  generated files, not screenshots: open one and it behaves like the deck it
  came from. The gallery links to every one it has a card for.
- `assets/` — the brand images the landing page uses: the hero, the framed
  figure, and the social/SEO cover.
- `functions/` — two Cloudflare Pages Functions, `e.js` and `SKILL.md.js`.
- `.github/workflows/deploy-pages.yml` — the deploy.

**In the skill repository, read at build time**

- `templates/templates.json` — the registry the gallery is built from.
- `templates/thumbs/*.png` — the gallery thumbnails.
- `assets/tedandlisa-intake.html` — the intake panel served at `/intake.html`.
- `assets/monomind-mark-white.svg` — the MonoMind mark, which also becomes the
  page's solid-white variant and the favicon.

Splitting the site out of the skill was a packaging decision, not a decision to
keep two copies of the gallery. The registry, the panel and the thumbnails stay
canonical where the skill is, and the build reaches across for them — so a
template added to the skill appears on the website with nothing here to update.


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
checks out both repositories, runs the skill repository's
`scripts/tedandlisa_intake_fallback.py --check` as a gate — the intake panel
carries a generated fallback template list for `file://` use, and a drifted one
would ship a gallery missing a template — then `site/sync.sh`, then
`wrangler pages deploy site` from the repository root.

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
