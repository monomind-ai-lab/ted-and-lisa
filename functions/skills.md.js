/**
 * GET /skills.md — a 301 to /SKILL.md, nothing more.
 *
 * People (and marketing copy) type the lowercase plural, and Pages Functions
 * routing is file-based and exact — /skills.md matched nothing and answered
 * 404. An agent pointed at the misremembered URL then builds from a 404 page
 * instead of the skill.
 *
 * A redirect rather than a second copy of the proxy in functions/SKILL.md.js:
 * the skill keeps exactly one public URL, so the edge cache, the x-source
 * header and any future change to the proxy live in one place, and the alias
 * holds no content that could drift. Agents' HTTP fetchers follow a
 * same-origin redirect, so the cost is one extra round trip on first fetch —
 * and the 301 is itself cacheable, so usually not even that.
 *
 * Why a function and not a _redirects file: the deploy has exactly one
 * routing mechanism today — wrangler compiling functions/ from the repository
 * root (see the note at the top of functions/SKILL.md.js) — and site/ is an
 * assembled folder whose canonical-file inventory site/sync.sh documents.
 * One more one-purpose function keeps it that way.
 *
 * (No lowercase-singular sibling: a functions/skill.md.js would collide with
 * functions/SKILL.md.js on the case-insensitive filesystems this repository
 * is developed on.)
 */

export function onRequest() {
  return new Response(null, {
    status: 301,
    headers: {
      location: "/SKILL.md",
      /* Permanent and boring — let browsers and edges keep it for a day. */
      "cache-control": "public, max-age=86400"
    }
  });
}
