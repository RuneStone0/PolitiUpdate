"""Which updates belong to the same CASE — not just the same press release.

The Ritzau feed re-announces one press-release *page* under a new ``#sm-`` id on
every police update, and the police also publish *new pages* about a case that is
already running (a live notice, then the follow-up, then the court outcome). Both
show up in a briefing as separate entries, so a reader sees the same case two or
three times, and the "5 most read stories" block can end up with 3 distinct cases
in 5 slots (measured on the delivered week-39 briefing: highlights 3+5 were both
"E. Hansens Vej, Esbjerg" and 2+4 were both "Brøndbyøster Station").

Two deterministic keys, no LLM:

* ``page_key`` — the press-release URL without the ``#sm-`` fragment. Exact: same
  page means the same case (this is what ``dedupe_visible`` half-caught).
* ``venues`` — named **locations** mentioned in the title or body: a run of
  capitalised words whose last word ends in a venue suffix (vej, gade, allé,
  plads, station, skole, center, kirke, bro, havn, motorvej …), normalised so
  "E. Hansens Vej", "E. Hansensvej" and "e hansensvej" collapse to one key.
  Same district + a shared venue = same case.

Deliberately NOT a signal: ordinary shared words. Measured on week 39, a
"rare token" rule (df <= 3) merged two *different* missing persons
("Efterlysning 21 årig kvinde i Tylstrup" with "dement 73 årig mand
Frederikshavn") on the tokens ``søger`` + ``værende``, and a knallert case with
an unrelated court case on ``bøde`` + ``frakendelse`` — 10 false merges for the
2 real ones. A city name alone is too coarse as well (every court story in one
city would merge), so the anchor must be a street/venue-like name.

Consequence for the reader: counts (subject, intro, "… og N flere") keep stating
the week's real number of **updates**; only the listing collapses, and a
collapsed entry says how many updates the case has.
"""

from __future__ import annotations

import re
from itertools import chain

from src.bot.formatter import _district_prefix as district_short_name

# A venue name must END with one of these. Street/road suffixes are specific
# enough on their own ("Nymøllevej", "Ebeltoftvej"), so a single word qualifies.
STREET_SUFFIXES: tuple[str, ...] = (
    "landevejen", "landevej", "boulevarden", "boulevard", "alléen", "allé",
    "pladsen", "plads", "gaden", "gade", "vejen", "vej",
)
# Venue-word suffixes are also ordinary Danish words and several city names end
# in them ("Frederikshavn", "Rødbyhavn", "politistation"), so these only count as
# an anchor when they are part of a MULTI-word name ("Brøndbyøster Station",
# "Østjyske Motorvej", "Grundtvigs Allé").
VENUE_WORD_SUFFIXES: tuple[str, ...] = (
    "motorvejen", "motorvej", "stationen", "station", "skolen", "skole",
    "centret", "center", "kirken", "kirke", "torvet", "torv", "gården", "gård",
    "broen", "bro", "havnen", "havn", "stranden", "strand", "parken", "park",
)
VENUE_SUFFIXES: tuple[str, ...] = STREET_SUFFIXES + VENUE_WORD_SUFFIXES

_TOKEN = re.compile(r"[^\W\d_]+(?:[.'-][^\W\d_]+)*", re.UNICODE)
_SUFFIX_KEYS = tuple(sorted({s for s in VENUE_SUFFIXES}, key=len, reverse=True))


def _is_capitalised(token: str) -> bool:
    """Danish proper-noun-ish: leading capital, or an all-caps headline word."""
    if not token:
        return False
    if token.isupper() and len(token) > 1:
        return True
    return token[0].isupper()


def normalise(text: str) -> str:
    """Collapse a place name to a comparison key: 'E. Hansens Vej' -> 'ehansensvej'."""
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def venues(post: dict) -> set[str]:
    """Named locations in this post's title and body, as normalised keys."""
    out: set[str] = set()
    for field in ("title", "body"):
        text = post.get(field) or ""
        tokens = [m.group(0) for m in _TOKEN.finditer(text)]
        capital = [_is_capitalised(t) for t in tokens]
        i = 0
        while i < len(tokens):
            if not capital[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(tokens) and capital[j + 1]:
                j += 1
            run = tokens[i:j + 1]
            key = normalise("".join(run))
            if _is_venue(key, len(run)):
                out.add(key)
            # keep scanning inside the run: "Brøndbyøster Station skole" etc.
            i += 1
    return out


def _is_venue(key: str, run: int) -> bool:
    """A capitalised run is a venue anchor only if it carries a real stem.

    One word must match a **street** suffix by itself ("Nymøllevej"); a
    venue-word suffix ("station", "havn", "motorvej") needs a second word, or the
    common noun itself — or a city like Frederikshavn — becomes an anchor and
    unrelated cases merge. Measured on week 39: "Østjyske Motorvej" and
    "Vestmotorvejen" both collapsed to ``motorvejen`` before this rule.
    """
    if run < 2:
        longest = max((s for s in VENUE_SUFFIXES if key.endswith(s)), key=len, default="")
        # The longest match must be a *street* suffix: "motorvej" and
        # "Frederikshavn" also end in "vej"/"havn", and accepting those by their
        # shorter ending is how generic road words became anchors.
        return longest in STREET_SUFFIXES and len(key) - len(longest) >= 3
    return any(key.endswith(s) and len(key) > len(s) for s in VENUE_SUFFIXES)


def page_key(post: dict) -> str:
    """The press-release page this post belongs to (``#sm-`` fragment stripped)."""
    return (post.get("guid") or "").split("#")[0].rstrip("/")


def title_key(post: dict) -> str:
    """Normalised headline — used only as a fallback identity (see group_by_case)."""
    return " ".join((post.get("title") or "").split()).casefold()


def _district(post: dict) -> str:
    """Canonical district key, ignoring the authority wrapper.

    "Anklagemyndigheden ved Københavns Vestegns Politi" and "Københavns Vestegns
    Politi" are the same district, and a case must not stay split because the
    prosecution messages carry the wrapper (measured on week 39: the
    Brøndbyøster Station incident and its court outcome only merged once the
    wrapper was stripped).
    """
    name = (post.get("district") or "").strip()
    if not name:
        return ""
    try:
        return district_short_name(name).casefold() or name.casefold()
    except Exception:  # noqa: BLE001 - never let presentation break a send
        return name.casefold()


def group_by_case(posts: list[dict]) -> list[list[dict]]:
    """Cluster posts that describe the same case, in posting order.

    Three keys, strongest first:
      * ``page_key`` — the same press-release page: the police re-announce one
        page on every update, which is where the 29 repeated rows in week 39 came
        from;
      * ``(district, venue)`` — the incident and its later court outcome are two
        different pages about one named place;
      * the headline, **only** for rows that carry no page identity at all (no
        ``guid``), because two unrelated cases can share a headline.
    """
    order = list(posts)
    index = {id(p): i for i, p in enumerate(order)}
    parent = list(range(len(order)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    by_page: dict[str, int] = {}
    by_venue: dict[tuple[str, str], int] = {}
    by_title: dict[str, int] = {}
    for i, post in enumerate(order):
        page = page_key(post)
        if page:
            if page in by_page:
                union(i, by_page[page])
            else:
                by_page[page] = i
        for venue in venues(post):
            slot = (_district(post), venue)
            if slot in by_venue:
                union(i, by_venue[slot])
            else:
                by_venue[slot] = i
        if not page:
            title = title_key(post)
            if title:
                if title in by_title:
                    union(i, by_title[title])
                else:
                    by_title[title] = i

    clusters: dict[int, list[dict]] = {}
    for i, post in enumerate(order):
        clusters.setdefault(find(i), []).append(post)
    out = sorted(clusters.values(), key=lambda c: index[id(c[0])])
    return out


def is_stub(post: dict) -> bool:
    """A teaser/placeholder update with no information beyond "we're on it".

    These must never be the text of a highlight when the case has a real update:
    week 39's most-read post was "Vi er i øjeblikket til stede på E. Hansens Vej i
    Esbjerg, hvor vi undersøger et mistænkeligt forhold. Vi opdaterer hurtigst
    muligt." — 2,643 views of a sentence that says nothing.
    """
    body = " ".join((post.get("body") or "").split()).casefold()
    if len(body) < 90:
        return True
    return any(
        marker in body
        for marker in (
            "opdaterer hurtigst muligt", "vi opdaterer", "opdateres hurtigst",
            "vi vender tilbage", "mere information følger",
        )
    )


def represent(cluster: list[dict], views: dict[str, int] | None = None) -> dict:
    """How a briefing shows one case: its latest word, ranked by its reach.

    Returns ``{"post", "link_post", "updates", "rank_views", "stub_only"}``:
      * ``post`` — the case's **newest non-stub** update (a teaser such as "vi
        opdaterer hurtigst muligt" is only shown when the case has nothing else),
        because a reader wants the case as it stands now,
      * ``link_post`` — the same post, so the text and the link always agree,
      * ``updates`` — how many posted updates the case had (never hidden),
      * ``rank_views``— the case's most-viewed update, so "flest har læst" ranks
        cases while the displayed text is the latest one.
    """
    views = views or {}

    def views_of(post: dict) -> int:
        return int(views.get(str(post.get("x_post_id")), 0) or 0)

    informative = [p for p in cluster if not is_stub(p)]
    post = (informative or cluster)[-1]
    return {
        "post": post,
        "link_post": post,
        "updates": len(cluster),
        "rank_views": max((views_of(p) for p in cluster), default=0),
        "stub_only": not informative,
    }


def all_venues(posts: list[dict]) -> dict[str, set[str]]:
    """Debug helper: venue keys per post id."""
    return {str(p.get("x_post_id")): venues(p) for p in posts}


def _self_test() -> int:
    """Offline assertions on real strings from the delivered briefings."""
    pairs = [
        # Esbjerg: same case, two different press-release pages and wordings.
        ({"title": "Politiet til stede i Esbjerg",
          "body": "Vi er i øjeblikket til stede på E. Hansens Vej i Esbjerg, hvor vi undersøger et mistænkeligt forhold.",
          "district": "Syd- og Sønderjyllands Politi", "guid": "https://x/1#sm-1"},
         {"title": "Vi er til stede med den mobile politistation på E. Hansensvej i Esbjerg",
          "body": "Den Mobile Politistation er til stede på E. Hansens Vej i Esbjerg i dag fra klokken 10.00 - 12.00.",
          "district": "Syd- og Sønderjyllands Politi", "guid": "https://x/2#sm-2"}),
        # Brøndbyøster: the incident and its court outcome.
        ({"title": "Episode på Brøndbyøster Station",
          "body": "Vi arbejder på Brøndbyøster Station, hvor en ung mand er blevet stukket med kniv.",
          "district": "Københavns Vestegns Politi", "guid": "https://x/3#sm-3"},
         {"title": "Ung mand varetægtsfængslet i fire uger for grov vold",
          "body": "Han er også mistænkt for forsøg på manddrab ved en episode, der fandt sted på Brøndbyøster Station den 23. september.",
          "district": "Københavns Vestegns Politi", "guid": "https://x/4#sm-4"}),
    ]
    for a, b in pairs:
        assert len(group_by_case([a, b])) == 1, (a["title"], b["title"])
        # and the venue is what links them, not the page
        assert venues(a) & venues(b), (a["title"], venues(a), venues(b))
    # Two different missing persons must stay apart (the naive token rule merged them).
    a = {"title": "Efterlysning dement 73 årig mand Frederikshavn",
         "body": "Vi søger en 73 årig mand, der er gået fra sin bopæl i Frederikshavn.",
         "district": "Nordjyllands Politi", "guid": "https://x/5#sm-5"}
    b = {"title": "Efterlysning 21 årig kvinde i Tylstrup",
         "body": "Vi søger en 21 årig kvinde, der er gående fra en adresse i Tylstrup.",
         "district": "Nordjyllands Politi", "guid": "https://x/6#sm-6"}
    assert len(group_by_case([a, b])) == 2
    # Two unrelated court cases in the same city must stay apart too.
    c = {"title": "Grundlovsforhør Retten i Sønderborg",
         "body": "En 30-årig mand fremstilles i grundlovsforhør i Sønderborg sigtet for vold.",
         "district": "Syd- og Sønderjyllands Politi", "guid": "https://x/7#sm-7"}
    d = {"title": "Grundlovsforhør ved Retten i Kolding den 24. september kl. 10.00",
         "body": "En 41-årig kvinde fremstilles i grundlovsforhør i Kolding sigtet for tyveri.",
         "district": "Sydøstjyllands Politi", "guid": "https://x/8#sm-8"}
    assert len(group_by_case([c, d])) == 2
    # Same page, different updates -> one case even with no venue.
    e = {"title": "Metro-trafikken på Cityringen midlertidigt indstillet",
         "body": "Vi undersøger et forhold ved Cityringen.", "district": "Københavns Politi",
         "guid": "https://x/9#sm-9"}
    f = dict(e, body="Vi er nu færdige med vores undersøgelser, og metroen kører igen.",
             guid="https://x/9#sm-10")
    assert len(group_by_case([e, f])) == 1
    assert "vej" not in venues({"title": "Vej", "body": "Vej"})
    assert normalise("E. Hansens Vej") == normalise("E. Hansensvej") == "ehansensvej"
    print("self-test OK — venue keys group the same case and keep different cases apart")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
