/**
 * GET /SKILL.md — the skill itself, proxied from the repository that owns it.
 *
 * https://html.monomind.one/SKILL.md is the stable public URL llms.txt
 * advertises to agents: point anything that can read a URL at it and it has
 * the whole procedure. The file behind it is not ours. It is canonical at
 * skills/lisa/SKILL.md in monomind-ai-lab/hi-ted-meet-lisa, where the plugin
 * manifests and the installed skill read it from.
 *
 * WHY A PROXY AND NOT A COPY. When the site lived in that repository, the
 * deploy simply copied the file into site/. It cannot now: the website is its
 * own repository, and a copy committed here would be a second original. It
 * would go stale the first time the skill changed and nobody noticed, and an
 * agent following the advertised URL would build against instructions the
 * skill no longer gives. A copy assembled at deploy time from the skill
 * checkout would be almost as bad — correct only as often as this repository
 * happens to deploy. Fetching it per request keeps one original and no
 * synchronisation to forget: publish the skill, and this URL is already it.
 *
 * The edge cache is what makes that affordable — a few minutes of freshness,
 * served stale while it revalidates, so the common case is a cache hit and
 * raw.githubusercontent.com sees a trickle rather than the traffic.
 *
 * On an upstream failure this answers 502 with a plain-text explanation
 * naming the URL it could not read. Never an empty 200: an agent handed a
 * blank document does not see an outage, it sees a skill with no
 * instructions, and builds something anyway.
 *
 * Wrangler compiles `functions/` from the *current working directory*, not
 * from the deploy directory — `wrangler pages deploy site` run at the
 * repository root finds this file here. Do not move it under site/: that
 * folder is assembled by site/sync.sh and wrangler would upload it as a
 * static asset instead of building it.
 */

const UPSTREAM =
  "https://raw.githubusercontent.com/monomind-ai-lab/hi-ted-meet-lisa/main/skills/lisa/SKILL.md";

/* Five minutes fresh, then an hour of serving the stale copy while the
   refresh happens behind it. A skill edit is public within minutes; an
   upstream blip is invisible for an hour. */
const CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=3600";

function badGateway(detail) {
  return new Response(
    "502 Bad Gateway\n\n" +
      "SKILL.md could not be read from its source repository.\n" +
      "Upstream: " + UPSTREAM + "\n" +
      detail + "\n\n" +
      "The skill is canonical at monomind-ai-lab/hi-ted-meet-lisa; read it\n" +
      "there while this is failing.\n",
    {
      status: 502,
      headers: {
        "content-type": "text/plain; charset=utf-8",
        "cache-control": "no-store"
      }
    }
  );
}

export async function onRequest(context) {
  const { request } = context;

  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response("405 Method Not Allowed\n", {
      status: 405,
      headers: {
        "content-type": "text/plain; charset=utf-8",
        allow: "GET, HEAD",
        "cache-control": "no-store"
      }
    });
  }

  let upstream;
  try {
    /* cf.cacheTtl caches the fetch itself at the edge, so a cold colo costs
       one origin read rather than one per visitor. */
    upstream = await fetch(UPSTREAM, {
      cf: { cacheTtl: 300, cacheEverything: true },
      headers: { accept: "text/plain" }
    });
  } catch (e) {
    return badGateway("Reason: the request failed (" + e + ").");
  }

  if (!upstream.ok) {
    return badGateway("Reason: upstream answered " + upstream.status + ".");
  }

  let body;
  try {
    body = await upstream.text();
  } catch (e) {
    return badGateway("Reason: the response body could not be read (" + e + ").");
  }

  /* An empty document is an outage wearing a 200. Treat it as one. */
  if (!body.trim()) {
    return badGateway("Reason: upstream answered 200 with an empty body.");
  }

  return new Response(body, {
    status: 200,
    headers: {
      "content-type": "text/markdown; charset=utf-8",
      "cache-control": CACHE_CONTROL,
      /* Where this actually came from, for anyone reading the headers. */
      "x-source": UPSTREAM
    }
  });
}
