"""Pure-data sample library: four demo Books sharing one canonical Story Library.

This module contains **no I/O, no ORM, no database access** — it only describes,
via frozen dataclasses and module-level tuples, what a seeder should later write to
the database. A separate seeding service (not this file) is responsible for turning
these specs into rows.

## The global-scenes / global-codex model

In Quillnight, ``scenes`` and ``codex_entries`` are **canonical and global** — they
are not owned by any single Book. A Book only *references* them, through join
tables (``book_scene_links`` / canvas membership, ``book_scene_order`` / outline+
timeline placement, ``book_codex_links`` / cast membership). That is what lets one
scene sit on two different Books' canvases at two different positions, and one
character belong to the cast of two different Books at once — both of which this
file deliberately demonstrates (see the ``# EDGE CASE:`` comments below).

Concretely, this module keeps two "pools" at the top level, keyed by a stable
string key rather than a real UUID (the seeder mints real UUIDs and keeps a
key -> id map when it inserts):

* ``SCENES`` — every canonical scene/plot-point/thought node across the whole
  library.
* ``CODEX_ENTRIES`` — every canonical character/location/faction/object_lore
  entry across the whole library.

Each ``BookSpec`` then only holds *per-Book* data: its own chapters, its own
canvas-node placements (position/color/archived, referencing a scene key), its
own edges (``scene_connections``), and its own outline/timeline ordering rows.
Codex membership, relationships, arc states, images, continuity flags, and
revisions are kept as separate flat, library-wide tuples (mirroring how their
underlying tables are not Book-scoped, or are Book-scoped via a foreign key
rather than nesting) so one lookup key never has to be threaded through nested
structures more than once.

## Shared world

All four Books share one loosely-connected setting: a rain-soaked harbor city
governed by a guild of lantern-keepers, and a flooded-neon nightlife district
called the Vespers District that grew up around the old lantern piers once
electricity made the guild's original purpose obsolete.
"""

from __future__ import annotations

from dataclasses import dataclass


# ── Dataclasses ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SceneSpec:
    key: str
    node_type: str
    title: str
    description: str | None
    status: str


@dataclass(frozen=True)
class ChapterSpec:
    key: str
    title: str
    order_index: int


@dataclass(frozen=True)
class CanvasNodeSpec:
    scene_key: str
    x: float
    y: float
    color: str | None = None
    archived: bool = False


@dataclass(frozen=True)
class EdgeSpec:
    source_key: str
    target_key: str
    connection_type: str | None
    label: str | None = None
    sequence_weight: int | None = None


@dataclass(frozen=True)
class OrderSpec:
    scene_key: str
    chapter_key: str | None
    outline_order_index: int
    structure_beat: str | None
    timeline_order_index: int | None
    in_story_time_label: str | None
    in_story_time_sort_key: float | None


@dataclass(frozen=True)
class ScreenplayElementSpec:
    scene_key: str
    order_index: int
    element_type: str
    text: str


@dataclass(frozen=True)
class CodexSpec:
    key: str
    entry_type: str
    name: str
    summary: str
    custom_fields: dict | None = None
    portrait_image_key: str | None = None


@dataclass(frozen=True)
class CodexBookLinkSpec:
    codex_key: str
    book_key: str
    role_note: str | None = None


@dataclass(frozen=True)
class CodexSceneLinkSpec:
    codex_key: str
    scene_key: str
    note: str | None = None


@dataclass(frozen=True)
class RelationshipSpec:
    from_key: str
    to_key: str
    relationship_type: str
    description: str | None = None


@dataclass(frozen=True)
class ArcStateSpec:
    codex_key: str
    book_key: str
    as_of_outline_order_index: int
    status_summary: str
    traits_snapshot: dict | None = None


@dataclass(frozen=True)
class ImageSpec:
    key: str
    kind: str  # 'cover' | 'scene' | 'portrait'
    bucket: str
    display_name: str
    description: str | None
    tags: tuple[str, ...]
    seed: str


@dataclass(frozen=True)
class EntityImageSpec:
    image_key: str
    entity_type: str  # 'book' | 'scene' | 'codex_entry'
    entity_key: str
    role: str | None = None
    order_index: int | None = None


@dataclass(frozen=True)
class ContinuityFlagSpec:
    book_key: str
    scene_key: str | None
    codex_key: str | None
    flag_type: str
    severity: str
    description: str
    status: str
    source: str


@dataclass(frozen=True)
class RevisionSpec:
    scene_key: str
    revision_number: int
    title: str
    description: str | None
    status: str | None
    change_source: str
    note: str | None = None


@dataclass(frozen=True)
class BookSpec:
    key: str
    title: str
    book_type: str
    logline: str
    front_matter: dict
    structure_template_name: str | None  # 'Three-Act' | "Hero's Journey" | 'Freeform' | None
    cover_image_key: str | None
    chapters: tuple[ChapterSpec, ...]
    canvas: tuple[CanvasNodeSpec, ...]
    edges: tuple[EdgeSpec, ...]
    order: tuple[OrderSpec, ...]


# Legal enum values, kept here once so _validate() and future maintainers share
# a single source of truth for what the DB's CHECK constraints allow.
_BOOK_TYPES = {"story_book", "movie_script", "short_film_script", "single_scene"}
_NODE_TYPES = {"scene", "plot_point", "thought"}
_STATUSES = {"draft", "revised", "final"}
_CONNECTION_TYPES = {"sequence", "causal", "reference", "contradiction", "custom", None}
_ELEMENT_TYPES = {
    "scene_heading",
    "action",
    "character",
    "dialogue",
    "parenthetical",
    "transition",
    "shot",
    "dual_dialogue",
}
_ENTRY_TYPES = {"character", "location", "faction", "object_lore"}
_BUCKETS = {"finalized_scene", "reference_pool"}
_IMAGE_KINDS = {"cover", "scene", "portrait"}
_ENTITY_TYPES = {"book", "scene", "codex_entry"}
_FLAG_TYPES = {"early_appearance", "trait_contradiction", "timeline_conflict", "custom"}
_SEVERITIES = {"critical", "warning", "hint"}
_FLAG_STATUSES = {"open", "dismissed", "resolved"}
_FLAG_SOURCES = {"deterministic", "ai", "manual"}
_CHANGE_SOURCES = {"manual_edit", "enhance_accept", "ai_merge", "restore"}
_STRUCTURE_TEMPLATE_NAMES = {"Three-Act", "Hero's Journey", "Freeform", None}


# ── Scenes: THE LANTERN-KEEPER'S DEBT (story_book, Three-Act) ──────────────────
# A shared canonical scene, deliberately placed on two Books' canvases at two
# different positions (see EDGE CASE comments on the canvas nodes below):
# `harbor_fog_intro` establishes the same physical harbor location that both
# `lantern` (as its opening image) and `vespers` (as a flashback beat) draw on.
_SHARED_SCENE = SceneSpec(
    key="harbor_fog_intro",
    node_type="scene",
    title="Fog on the Lantern Piers",
    description=(
        "Fog rolls off the black water in slow ropes, swallowing the pier lanterns one by "
        "one until only their auras remain, hanging in the mist like open eyes.\n\n"
        "A lone keeper works the wick-line, boots ringing on wet iron grating, breath "
        "fogging in time with the harbor bell three docks over. Somewhere below, water "
        "slaps against a hull nobody has claimed in eleven years.\n\n"
        "This is the harbor before either story starts — the place both of them keep "
        "returning to, whether they know it or not."
    ),
    status="draft",
)

_LANTERN_SCENES = (
    SceneSpec(
        key="lantern_opening_debt",
        node_type="scene",
        title="The Ledger Comes Due",
        description=(
            "Mireille Ashgrove has kept the Northpier lantern alight for six years without "
            "missing a single dusk, and tonight the Lantern-Keepers' Guild is going to take "
            "that away from her over a debt she didn't create.\n\n"
            "The guild-master's letter sits unopened on the lighthouse table between two cold "
            "cups of tea, its wax seal the exact rust-orange of a warning flare. She knows what "
            "it says before she breaks it: her late father's debt to the guild, quietly "
            "compounding for a decade, has finally come due, and the only currency the guild "
            "will accept from a keeper without coin is service — dangerous, unspecified "
            "service, out past the breakwater, in the dark.\n\n"
            "She lights the lantern anyway. Some things you do out of duty even when duty is "
            "about to cost you the only home you've ever loved."
        ),
        status="draft",
    ),
    SceneSpec(
        key="lantern_guildhall_summons",
        node_type="scene",
        title="Summoned to the Guildhall",
        description=(
            "The Lantern-Keepers' Guildhall smells of whale oil and old brass even now, "
            "decades after the last whaling ship left this harbor for good — the guild "
            "keeps the smell on purpose, Mireille has always suspected, the way some men "
            "keep a war wound they're secretly proud of.\n\n"
            "Guild-Master Corvin Thale receives her in a study lined with logbooks going "
            "back two hundred years, and does not offer her a chair. He explains her "
            "father's debt in the patient, regretful tone of a man who has personally "
            "decided to enjoy this. The debt, he says, can be settled one of two ways: the "
            "Northpier light goes dark and the tower reverts to the guild, or she carries a "
            "sealed lantern out to Wraith Shoal and lights it there, where no keeper has "
            "gone and returned in living memory."
        ),
        status="draft",
    ),
    SceneSpec(
        key="lantern_meets_saoirse",
        node_type="scene",
        title="A Smuggler's Offer",
        description=(
            "Saoirse Vane finds Mireille at the exact bar Saoirse always finds people at, "
            "which is either a coincidence or proof that Saoirse has been watching the "
            "guildhall's front steps all week waiting for someone desperate enough to be "
            "useful.\n\n"
            '"Wraith Shoal," Saoirse repeats, turning the words over like they taste '
            "interesting. \"I know a channel through the rocks the guild doesn't have on any "
            "chart. I'll take you out there for a price you're not going to like, and a "
            "second price you're going to like even less.\"\n\n"
            "Mireille doesn't trust her, not even slightly. She hires her anyway, because the "
            "tide window closes in four days and trust is a luxury for people who aren't "
            "about to lose their tower."
        ),
        status="draft",
    ),
    SceneSpec(
        key="lantern_first_argument",
        node_type="scene",
        title="A Difference of Opinion",
        description=(
            "They fight about the route before they've even cleared the harbor mouth — "
            "Mireille wants the long way around the sandbar the guild's charts warn about; "
            "Saoirse wants the short way through water the guild's charts don't mention at "
            "all, which Mireille finds significantly less reassuring than Saoirse seems to "
            "intend it to be.\n\n"
            '"Your charts are drawn by men who\'ve never once gotten their boots wet," '
            "Saoirse says, and there's an old bitterness under it that makes Mireille look at "
            "her a second time."
        ),
        status="draft",
    ),
    SceneSpec(
        key="lantern_wraith_shoal_arrival",
        node_type="thought",
        title="Wraith Shoal, At Last",
        description=(
            "A note, half to herself: the shoal doesn't look haunted so much as *tired* — "
            "rocks worn smooth in shapes that almost resemble hands reaching up out of the "
            "water, reaching for a light that hasn't shone here in a hundred years.\n\n"
            "Mireille writes it down because she has learned, the hard way, that the "
            "feelings you get in places like this are data, not decoration."
        ),
        status="draft",
    ),
    SceneSpec(
        key="lantern_the_old_wreck",
        node_type="scene",
        title="What the Shoal Kept",
        description=(
            "The wreck under the shoal isn't a ship. It's a lantern tower, older than the "
            "guild itself, half-swallowed by rock and coral and a century of silt, its "
            "lens chamber somehow still intact behind a lattice of dead barnacles.\n\n"
            "Saoirse goes very quiet in a way Mireille hasn't seen from her yet. \"My mother "
            'used to tell me a story about a tower the sea ate," she says. "I thought it was '
            "just a story to scare keepers' children into checking their moorings twice.\"\n\n"
            "Mireille runs a hand along the lens housing and feels something under the grime "
            "that is unmistakably, impossibly, still faintly warm."
        ),
        status="draft",
    ),
    SceneSpec(
        key="lantern_saoirse_secret",
        node_type="plot_point",
        title="Reveal: Saoirse's Grandmother",
        description=(
            "Saoirse admits it in pieces, the way people confess things they've been "
            "carrying too long: her grandmother was a Northpier keeper too, decades before "
            "Mireille's father, and was the one who *sealed* the old drowned tower rather "
            "than let the guild claim its light for its own purposes.\n\n"
            "The debt on Mireille's father was never really about money. It was the guild "
            "quietly, patiently trying to buy back the location Saoirse's grandmother took "
            "to her grave."
        ),
        status="draft",
    ),
    SceneSpec(
        key="lantern_the_ambush",
        node_type="scene",
        title="The Guild Was Already Here",
        description=(
            "Guild skiffs come out of the fog with their running lights doused, which tells "
            "Mireille everything she needs to know about how long Corvin Thale has been "
            "planning this and how little he intended to let her actually settle the debt "
            "on her own terms.\n\n"
            '"You were never meant to light it and come home," a guild officer calls across '
            "the water, almost gently, as if this is a kindness he's doing her by saying it "
            'out loud. "The debt was never the point. The location was."\n\n'
            "Saoirse's hand finds the tiller before Mireille's does. \"Then we'd better make "
            'sure lighting it is the last thing they expect," she says.'
        ),
        status="draft",
    ),
    SceneSpec(
        key="lantern_choice_confrontation",
        node_type="scene",
        title="Northpier or the Shoal",
        description=(
            "Cornered against the wreck's exposed lens chamber, Mireille understands the "
            "shape of the choice Thale has actually offered her, underneath all the paperwork: "
            "hand over the drowned tower's light and keep Northpier, or refuse him and lose "
            "everything, including, possibly, Saoirse.\n\n"
            "She thinks about her father lighting Northpier every dusk for thirty years "
            "without once explaining why it mattered so much to him. She thinks she finally "
            "understands.\n\n"
            '"No," she says, and means it as more than an answer to Thale.'
        ),
        status="draft",
    ),
    SceneSpec(
        key="lantern_lighting_the_old_lantern",
        node_type="scene",
        title="Lighting the Drowned Lantern",
        description=None,
        status="revised",
    ),
    SceneSpec(
        key="lantern_debt_paid",
        node_type="scene",
        title="A Debt Paid Differently",
        description=(
            "The drowned lantern comes alight for the first time in a hundred years, and "
            "the guild skiffs — every one of them — simply stop, engines idling, as if the "
            "light itself is a debt they didn't know they owed and are only now being asked "
            "to pay.\n\n"
            "Thale doesn't try to stop her taking Saoirse's grandmother's secret back to "
            "Northpier. Some debts, once seen clearly, aren't worth collecting anymore."
        ),
        status="final",
    ),
    SceneSpec(
        key="lantern_epilogue_northpier",
        node_type="scene",
        title="Two Lights Now",
        description=(
            "Northpier burns every dusk again, same as always, except now Mireille keeps a "
            "second small lamp lit on the sill beside it, facing out toward Wraith Shoal, "
            "for a tower that finally gets to be remembered instead of merely drowned.\n\n"
            "Saoirse stays. Neither of them makes a speech about it. She just stops leaving."
        ),
        status="final",
    ),
)

# ── Scenes: NEON VESPERS (movie_script, Hero's Journey) ────────────────────────
_VESPERS_SCENES = (
    SceneSpec(
        key="vespers_ordinary_arcade",
        node_type="scene",
        title="Rooftop Circuits",
        description=(
            "Kesh Okonkwo-Lin fixes drone racers for tourists on a rooftop above the Vespers "
            "District, close enough to the old lantern piers that the neon down below still "
            "flickers pier-lantern-orange on nights the district's power grid hiccups.\n\n"
            "It's a small life and Kesh has made peace with it, mostly, the way you make "
            "peace with a life you chose specifically because it was too small for anyone to "
            "come looking for you in it."
        ),
        status="draft",
    ),
    SceneSpec(
        key="vespers_call_signal",
        node_type="scene",
        title="A Signal Nobody Should Be Sending",
        description=(
            "A drone Kesh is repairing picks up a distress ping on a frequency the old "
            "lantern-keeper's guild retired forty years ago — a frequency that shouldn't "
            "exist anymore, transmitting from somewhere under the flooded piers.\n\n"
            "Kesh almost deletes the log. Almost."
        ),
        status="draft",
    ),
    SceneSpec(
        key="vespers_refusal_landlord",
        node_type="scene",
        title="Not My Problem",
        description=(
            "Kesh's landlord wants three months' back rent by Friday, and going looking for "
            "a mystery signal under the flooded district instead of taking paying repair "
            "jobs is, by any reasonable measure, an insane use of four days.\n\n"
            '"I\'m not the person for this," Kesh says out loud, to nobody, which is usually '
            "the first sign that Kesh is about to become exactly that person."
        ),
        status="draft",
    ),
    SceneSpec(
        key="vespers_mentor_thale_jr",
        node_type="scene",
        title="The Old Keeper's Grandson",
        description=(
            "Emeric Thale runs a pawn shop that used to be a lantern-supply store, and still "
            "keeps his grandfather's old guild maps rolled up behind the counter out of "
            "habit rather than sentiment, he insists, several times, unconvincingly.\n\n"
            "He recognizes the frequency immediately and goes pale in a way that makes Kesh "
            "very sure this is a much bigger problem than a broken drone."
        ),
        status="draft",
    ),
    SceneSpec(
        key="vespers_threshold_flooded_gate",
        node_type="scene",
        title="Through the Flood Gate",
        description=(
            "The old lantern district's drowned lower level is sealed behind a flood gate "
            "nobody has opened since the Vespers District was built on top of it, and "
            "opening it now means admitting, out loud, that Kesh is doing this.\n\n"
            "The gate groans open on hinges that have not moved in forty years. Below, "
            "impossibly, something is still faintly lit."
        ),
        status="draft",
    ),
    SceneSpec(
        key="vespers_ordeal_current",
        node_type="scene",
        title="Caught in the Undertow",
        description=(
            "The flooded corridor's current turns vicious exactly when Kesh is furthest "
            "from any exit, dragging toward a shaft that drops straight down into black "
            "water with no visible bottom.\n\n"
            "Emeric's borrowed rope holds. Barely. Kesh comes up gasping, alive, and closer "
            "than ever to whatever is making that light."
        ),
        status="draft",
    ),
    SceneSpec(
        key="vespers_reward_source",
        node_type="scene",
        title="The Source",
        description=(
            "The signal is coming from a lantern mechanism identical to the drowned one at "
            "Wraith Shoal, sealed behind guild ironwork generations before Kesh was born — "
            "proof the guild built more than one hidden light, and hid the fact even more "
            "carefully than the light itself.\n\n"
            "Kesh doesn't fully understand what it means yet. Understanding it is clearly "
            "going to be somebody else's problem before this is over, and equally clearly, "
            "that somebody is now Kesh."
        ),
        status="draft",
    ),
    SceneSpec(
        key="vespers_return_district",
        node_type="scene",
        title="Back Above the Waterline",
        description=(
            "Kesh surfaces into the ordinary neon glare of the Vespers District with rent "
            "still due Friday and absolutely no way to explain any of this to a landlord, "
            "carrying instead something far heavier than an explanation ever could be: proof "
            "that the district's whole foundation is built on a secret the guild never "
            "finished burying."
        ),
        status="draft",
    ),
)

# ── Scenes: SALT (short_film_script, Three-Act, no chapters) ───────────────────
_SALT_SCENES = (
    SceneSpec(
        key="salt_opening_kitchen",
        node_type="scene",
        title="The Last Batch",
        description=(
            "Old Ren works the salt pans at dawn the way she has for fifty years, raking "
            "white crystal into drying rows while the harbor mist burns off around her, "
            "unhurried, exact, a ritual disguised as labor.\n\n"
            "Her granddaughter watches from the seawall, phone in hand, filming for a video "
            "essay about vanishing trades that Ren has not agreed to be part of and does not "
            "yet know she's the subject of."
        ),
        status="draft",
    ),
    SceneSpec(
        key="salt_the_notice",
        node_type="plot_point",
        title="Eviction by Development Notice",
        description=(
            "A city notice arrives taped to the pan-house door: the salt flats have been "
            "sold to a developer building waterfront condominiums, and Ren has ninety days "
            "to vacate land her family has worked since before the harbor had a proper "
            "name."
        ),
        status="draft",
    ),
    SceneSpec(
        key="salt_granddaughter_pushes",
        node_type="scene",
        title="Fight or Film",
        description=(
            "Ren's granddaughter wants to turn the eviction into a viral campaign; Ren wants "
            "to be left alone to finish the season's harvest like it might be her last, "
            "which — unspoken between them — it very well might be.\n\n"
            '"You don\'t get to save something by filming it," Ren says, not unkindly, and '
            "goes back to raking."
        ),
        status="draft",
    ),
    SceneSpec(
        key="salt_final_harvest",
        node_type="scene",
        title="What the Salt Remembers",
        description=(
            "On the last legal morning before the notice takes effect, Ren lets her "
            "granddaughter finally film — not the protest video the girl wanted, but the "
            "raking itself, unbroken, in real time, fifty years of a body that knows exactly "
            "where to put its weight.\n\n"
            "It airs online with no narration at all. It is, against every prediction "
            "anyone made about it, the thing that finally makes people look up from their "
            "phones."
        ),
        status="final",
    ),
)

# ── Scenes: THE LAST BUS (single_scene, Freeform) ───────────────────────────────
_LASTBUS_SCENES = (
    SceneSpec(
        key="lastbus_only_scene",
        node_type="scene",
        # EDGE CASE: unicode/emoji AND a deliberately very long title (~120-140 chars) in one.
        title=(
            "The Last Bus Out of the Vespers District 🚌✨ — the exact moment staying stops "
            "being the harder choice, forty years after the lanterns went dark"
        ),
        description=(
            "The last bus out of the Vespers District idles at the flooded curb at 2 a.m., "
            "door open, driver patient in the specific way of someone who has made this same "
            "final run every night for a decade and has stopped expecting anyone to actually "
            "get on.\n\n"
            "Two strangers stand under the one working lantern-shaped streetlamp the "
            "district never got around to replacing — a keeper's granddaughter with a "
            "suitcase and nowhere it's actually packed for, and a bartender closing up the "
            "last bar on a street that used to have thirty of them.\n\n"
            "Neither of them gets on. They just watch it pull away, taillights smearing red "
            "through the standing water, and then, without discussing it, sit down together "
            "on the bus-stop bench to wait for whatever comes after last call instead."
        ),
        status="draft",
    ),
)

SCENES: tuple[SceneSpec, ...] = (
    (_SHARED_SCENE,) + _LANTERN_SCENES + _VESPERS_SCENES + _SALT_SCENES + _LASTBUS_SCENES
)


# ── Screenplay elements ──────────────────────────────────────────────────────
# `vespers_reward_source` exercises all 8 element_type values (including the
# dual_dialogue pair, Kesh / Emeric over the radio) in one sequence. The
# sequences below add coverage across more of the movie/short-film Books so
# `salt` isn't screenplay-blank and `vespers` isn't a single formatted scene:
# `vespers_ordinary_arcade` (cold open), `vespers_ordeal_current` (confrontation
# with the flooded corridor's current), `vespers_return_district` (climax/
# return, with its own dual_dialogue beat), and `salt_opening_kitchen` /
# `salt_final_harvest` (opening + closing beats of the short film).
SCREENPLAY_ELEMENTS: tuple[ScreenplayElementSpec, ...] = (
    ScreenplayElementSpec(
        scene_key="vespers_reward_source",
        order_index=0,
        element_type="scene_heading",
        text="INT. DROWNED LANTERN CHAMBER - CONTINUOUS",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_reward_source",
        order_index=1,
        element_type="action",
        text=(
            "Water drips from the ironwork lattice sealing a second lantern mechanism, "
            "identical to the one at Wraith Shoal. KESH's headlamp catches guild sigils "
            "scratched deliberately off the metal."
        ),
    ),
    ScreenplayElementSpec(
        scene_key="vespers_reward_source",
        order_index=2,
        element_type="shot",
        text="CLOSE ON - the scratched-out sigil, still faintly visible under the rust.",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_reward_source",
        order_index=3,
        element_type="character",
        text="KESH (V.O., RADIO)",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_reward_source",
        order_index=4,
        element_type="parenthetical",
        text="(breathless, static crackling)",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_reward_source",
        order_index=5,
        element_type="dialogue",
        text="Emeric. Emeric, there's a second one down here. The guild built two.",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_reward_source",
        order_index=6,
        element_type="dual_dialogue",
        text=(
            "KESH: Say something. Anything.  ||  "
            "EMERIC (RADIO): Get out of there right now, Kesh — that's not guild ironwork, "
            "that's a containment seal."
        ),
    ),
    ScreenplayElementSpec(
        scene_key="vespers_reward_source",
        order_index=7,
        element_type="transition",
        text="MATCH CUT TO:",
    ),
    # ── vespers_ordinary_arcade — cold open ──
    ScreenplayElementSpec(
        scene_key="vespers_ordinary_arcade",
        order_index=0,
        element_type="scene_heading",
        text="EXT. ROOFTOP ARCADE - VESPERS DISTRICT - NIGHT",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordinary_arcade",
        order_index=1,
        element_type="action",
        text=(
            "Neon bleeds up from the flooded streets below, catching on rows of drone "
            "racers lined up like toy soldiers. KESH OKONKWO-LIN, mid-20s, tool belt slung "
            "low, crouches over a cracked rotor housing."
        ),
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordinary_arcade",
        order_index=2,
        element_type="character",
        text="TOURIST (O.S.)",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordinary_arcade",
        order_index=3,
        element_type="dialogue",
        text="Can you fix it before the next race or not?",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordinary_arcade",
        order_index=4,
        element_type="character",
        text="KESH",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordinary_arcade",
        order_index=5,
        element_type="parenthetical",
        text="(not looking up)",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordinary_arcade",
        order_index=6,
        element_type="dialogue",
        text="Five minutes. Maybe four if you stop asking.",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordinary_arcade",
        order_index=7,
        element_type="action",
        text=(
            "She snaps the rotor into place and wipes grease on her jeans, glancing toward "
            "the old lantern piers glowing faint orange through the mist."
        ),
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordinary_arcade",
        order_index=8,
        element_type="shot",
        text="CLOSE ON - the rotor housing, a hairline crack sealing shut under her thumb.",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordinary_arcade",
        order_index=9,
        element_type="character",
        text="KESH",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordinary_arcade",
        order_index=10,
        element_type="parenthetical",
        text="(to herself)",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordinary_arcade",
        order_index=11,
        element_type="dialogue",
        text="Small life. Small problems. That's the deal.",
    ),
    # ── vespers_ordeal_current — confrontation with the flooded corridor ──
    ScreenplayElementSpec(
        scene_key="vespers_ordeal_current",
        order_index=0,
        element_type="scene_heading",
        text="INT. FLOODED CORRIDOR - CONTINUOUS",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordeal_current",
        order_index=1,
        element_type="action",
        text=(
            "The current slams KESH sideways into a support pillar. Her headlamp spins "
            "loose, strobing the black water in flashes."
        ),
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordeal_current",
        order_index=2,
        element_type="character",
        text="KESH",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordeal_current",
        order_index=3,
        element_type="parenthetical",
        text="(choking)",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordeal_current",
        order_index=4,
        element_type="dialogue",
        text="Emeric — the rope's not holding —",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordeal_current",
        order_index=5,
        element_type="character",
        text="EMERIC (RADIO)",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordeal_current",
        order_index=6,
        element_type="dialogue",
        text="It's holding. You're holding. Kick, Kesh, kick now.",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordeal_current",
        order_index=7,
        element_type="action",
        text=(
            "She kicks. The shaft below her yawns open, bottomless, and for one second the "
            "current wins."
        ),
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordeal_current",
        order_index=8,
        element_type="shot",
        text="WIDE - the corridor swallowing her light whole.",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordeal_current",
        order_index=9,
        element_type="action",
        text="Then the rope snaps taut. KESH breaks the surface, gasping, alive.",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_ordeal_current",
        order_index=10,
        element_type="transition",
        text="SMASH CUT TO:",
    ),
    # ── vespers_return_district — climax / return with the elixir ──
    ScreenplayElementSpec(
        scene_key="vespers_return_district",
        order_index=0,
        element_type="scene_heading",
        text="EXT. VESPERS DISTRICT STREET - NIGHT",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_return_district",
        order_index=1,
        element_type="action",
        text=(
            "KESH climbs out of a storm drain into the ordinary neon glare, soaked, "
            "holding a corroded sigil plate against her chest like it might still bite her."
        ),
    ),
    ScreenplayElementSpec(
        scene_key="vespers_return_district",
        order_index=2,
        element_type="action",
        text="EMERIC waits at the curb, engine idling, headlights cutting through the rain.",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_return_district",
        order_index=3,
        element_type="character",
        text="EMERIC",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_return_district",
        order_index=4,
        element_type="dialogue",
        text="Well?",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_return_district",
        order_index=5,
        element_type="character",
        text="KESH",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_return_district",
        order_index=6,
        element_type="dialogue",
        text=(
            "The guild built two. Two lanterns, two secrets, and only one of them ever got a name."
        ),
    ),
    ScreenplayElementSpec(
        scene_key="vespers_return_district",
        order_index=7,
        element_type="dual_dialogue",
        text=(
            "KESH: Rent's still due Friday.  ||  "
            "EMERIC: Then we'd better figure out what this is worth."
        ),
    ),
    ScreenplayElementSpec(
        scene_key="vespers_return_district",
        order_index=8,
        element_type="action",
        text="Neither of them laughs. Neither of them looks away from the plate either.",
    ),
    ScreenplayElementSpec(
        scene_key="vespers_return_district",
        order_index=9,
        element_type="shot",
        text=(
            "CLOSE ON - the scratched-out sigil, rain running through the grooves like "
            "it's trying to erase it twice."
        ),
    ),
    ScreenplayElementSpec(
        scene_key="vespers_return_district",
        order_index=10,
        element_type="transition",
        text="FADE OUT.",
    ),
    # ── salt_opening_kitchen — opening beat of the short film ──
    ScreenplayElementSpec(
        scene_key="salt_opening_kitchen",
        order_index=0,
        element_type="scene_heading",
        text="EXT. SALT FLATS - DAWN",
    ),
    ScreenplayElementSpec(
        scene_key="salt_opening_kitchen",
        order_index=1,
        element_type="action",
        text=(
            "Mist burns gold off the water as REN OKABE, seventies, rakes white crystal "
            "into drying rows with the unhurried exactness of fifty years of practice."
        ),
    ),
    ScreenplayElementSpec(
        scene_key="salt_opening_kitchen",
        order_index=2,
        element_type="action",
        text=(
            "On the seawall above, her granddaughter MIA lifts a phone, framing the shot "
            "without asking permission."
        ),
    ),
    ScreenplayElementSpec(
        scene_key="salt_opening_kitchen",
        order_index=3,
        element_type="character",
        text="MIA (O.S.)",
    ),
    ScreenplayElementSpec(
        scene_key="salt_opening_kitchen",
        order_index=4,
        element_type="dialogue",
        text="Just keep doing what you're doing.",
    ),
    ScreenplayElementSpec(
        scene_key="salt_opening_kitchen",
        order_index=5,
        element_type="character",
        text="REN",
    ),
    ScreenplayElementSpec(
        scene_key="salt_opening_kitchen",
        order_index=6,
        element_type="parenthetical",
        text="(not stopping)",
    ),
    ScreenplayElementSpec(
        scene_key="salt_opening_kitchen",
        order_index=7,
        element_type="dialogue",
        text="I always do.",
    ),
    ScreenplayElementSpec(
        scene_key="salt_opening_kitchen",
        order_index=8,
        element_type="shot",
        text=(
            "WIDE - the pans stretching to the harbor mouth, every row raked the same "
            "width for half a century."
        ),
    ),
    ScreenplayElementSpec(
        scene_key="salt_opening_kitchen",
        order_index=9,
        element_type="action",
        text="The rake never breaks rhythm. Ren doesn't look up once.",
    ),
    # ── salt_final_harvest — closing beat of the short film ──
    ScreenplayElementSpec(
        scene_key="salt_final_harvest",
        order_index=0,
        element_type="scene_heading",
        text="EXT. SALT FLATS - LAST MORNING",
    ),
    ScreenplayElementSpec(
        scene_key="salt_final_harvest",
        order_index=1,
        element_type="action",
        text=(
            "The notice's ninety days end at noon. REN starts the rake anyway, same "
            "rhythm, same rows, like the deadline is someone else's problem."
        ),
    ),
    ScreenplayElementSpec(
        scene_key="salt_final_harvest",
        order_index=2,
        element_type="character",
        text="MIA",
    ),
    ScreenplayElementSpec(
        scene_key="salt_final_harvest",
        order_index=3,
        element_type="dialogue",
        text="No narration. No music. Just you.",
    ),
    ScreenplayElementSpec(
        scene_key="salt_final_harvest",
        order_index=4,
        element_type="character",
        text="REN",
    ),
    ScreenplayElementSpec(
        scene_key="salt_final_harvest",
        order_index=5,
        element_type="parenthetical",
        text="(a long beat)",
    ),
    ScreenplayElementSpec(
        scene_key="salt_final_harvest",
        order_index=6,
        element_type="dialogue",
        text="Then don't cut away.",
    ),
    ScreenplayElementSpec(
        scene_key="salt_final_harvest",
        order_index=7,
        element_type="action",
        text=(
            "MIA lowers the phone to her side and simply presses record, holding the "
            "frame steady as Ren works the full length of the last row."
        ),
    ),
    ScreenplayElementSpec(
        scene_key="salt_final_harvest",
        order_index=8,
        element_type="shot",
        text=(
            "CLOSE ON - salt crystals catching the light exactly the way they have every "
            "dawn for fifty years."
        ),
    ),
    ScreenplayElementSpec(
        scene_key="salt_final_harvest",
        order_index=9,
        element_type="transition",
        text="FADE OUT.",
    ),
)


# ── Chapters (Lantern only — Salt and Last Bus deliberately have none) ─────────
_LANTERN_CHAPTERS = (
    ChapterSpec(key="lantern_ch1", title="The Debt", order_index=0),
    ChapterSpec(key="lantern_ch2", title="The Shoal", order_index=1),
    ChapterSpec(key="lantern_ch3", title="What Was Owed", order_index=2),
)


# ── Canvas layouts ───────────────────────────────────────────────────────────
# Readable left-to-right graphs, ~260px x-spacing, multiple rows (y = 0/200/400).
_LANTERN_CANVAS = (
    # EDGE CASE: `harbor_fog_intro` is the shared canonical scene — this is its
    # placement on `lantern`'s canvas (top row, far left, as the opening image).
    CanvasNodeSpec(scene_key="harbor_fog_intro", x=0, y=0),
    CanvasNodeSpec(scene_key="lantern_opening_debt", x=260, y=0),
    CanvasNodeSpec(scene_key="lantern_guildhall_summons", x=520, y=0),
    CanvasNodeSpec(scene_key="lantern_meets_saoirse", x=780, y=0, color="#c9884a"),
    CanvasNodeSpec(scene_key="lantern_first_argument", x=1040, y=200),
    CanvasNodeSpec(scene_key="lantern_wraith_shoal_arrival", x=1300, y=200),  # thought node
    CanvasNodeSpec(scene_key="lantern_the_old_wreck", x=1560, y=200),
    CanvasNodeSpec(scene_key="lantern_saoirse_secret", x=1820, y=200),  # plot_point node
    CanvasNodeSpec(scene_key="lantern_the_ambush", x=1560, y=400, color="#8a3b3b"),
    CanvasNodeSpec(scene_key="lantern_choice_confrontation", x=1820, y=400),
    CanvasNodeSpec(scene_key="lantern_lighting_the_old_lantern", x=2080, y=400),
    CanvasNodeSpec(scene_key="lantern_debt_paid", x=2340, y=200),
    CanvasNodeSpec(scene_key="lantern_epilogue_northpier", x=2600, y=0, color="#4a7a8a"),
    # EDGE CASE: a genuinely standalone orphan cut-scene idea, parked on the canvas
    # with no edges and no outline/timeline order row at all — an intentionally
    # valid "scene exists on canvas, not wired into anything yet" state. Also
    # exercises `archived=True` on a canvas node.
    CanvasNodeSpec(scene_key="lantern_orphan_idea", x=780, y=600, archived=True),
)

# The orphan needs its own scene row — added to _LANTERN_SCENES conceptually,
# but since tuples above are already frozen, it's appended into SCENES directly.
_LANTERN_ORPHAN_SCENE = SceneSpec(
    key="lantern_orphan_idea",
    node_type="thought",
    title="Unused Idea: The Guild's Missing Ledger Page",
    description=(
        "A stray note, never developed: what if the guild's copy of the original debt "
        "ledger is itself missing a page, and nobody currently alive knows it? Parked here "
        "in case a rewrite wants it."
    ),
    status="draft",
)
SCENES = SCENES + (_LANTERN_ORPHAN_SCENE,)

_VESPERS_CANVAS = (
    CanvasNodeSpec(scene_key="vespers_ordinary_arcade", x=0, y=0),
    CanvasNodeSpec(scene_key="vespers_call_signal", x=260, y=0),
    CanvasNodeSpec(scene_key="vespers_refusal_landlord", x=520, y=0),
    CanvasNodeSpec(scene_key="vespers_mentor_thale_jr", x=780, y=0, color="#c9884a"),
    CanvasNodeSpec(scene_key="vespers_threshold_flooded_gate", x=1040, y=0),
    # EDGE CASE: `harbor_fog_intro` is the SAME canonical scene as on `lantern`'s
    # canvas above, but placed here at a completely different position/row, used
    # as a flashback beat cut into the middle of Kesh's descent instead of an
    # opening image — demonstrating one scene, two Books, two independent layouts.
    CanvasNodeSpec(scene_key="harbor_fog_intro", x=1040, y=200, color="#4a7a8a"),
    CanvasNodeSpec(scene_key="vespers_ordeal_current", x=1300, y=0),
    CanvasNodeSpec(scene_key="vespers_reward_source", x=1560, y=0),
    CanvasNodeSpec(scene_key="vespers_return_district", x=1820, y=0),
)

_SALT_CANVAS = (
    CanvasNodeSpec(scene_key="salt_opening_kitchen", x=0, y=0),
    CanvasNodeSpec(scene_key="salt_the_notice", x=260, y=0),  # plot_point node
    CanvasNodeSpec(scene_key="salt_granddaughter_pushes", x=520, y=0),
    CanvasNodeSpec(scene_key="salt_final_harvest", x=780, y=0, color="#c9884a"),
)

_LASTBUS_CANVAS = (CanvasNodeSpec(scene_key="lastbus_only_scene", x=0, y=0),)


# ── Edges ───────────────────────────────────────────────────────────────────
_LANTERN_EDGES = (
    EdgeSpec("harbor_fog_intro", "lantern_opening_debt", "sequence", sequence_weight=10),
    EdgeSpec("lantern_opening_debt", "lantern_guildhall_summons", "sequence", sequence_weight=20),
    EdgeSpec(
        "lantern_guildhall_summons", "lantern_meets_saoirse", "causal", label="forces her hand"
    ),
    # EDGE CASE: connection_type=None — a loose, unresolved thematic link.
    EdgeSpec("lantern_meets_saoirse", "lantern_first_argument", None, label="uneasy partnership"),
    EdgeSpec(
        "lantern_first_argument", "lantern_wraith_shoal_arrival", "sequence", sequence_weight=45
    ),
    EdgeSpec(
        "lantern_wraith_shoal_arrival", "lantern_the_old_wreck", "sequence", sequence_weight=50
    ),
    EdgeSpec(
        "lantern_the_old_wreck", "lantern_saoirse_secret", "reference", label="explains the wreck"
    ),
    EdgeSpec("lantern_saoirse_secret", "lantern_the_ambush", "causal", label="guild was watching"),
    EdgeSpec("lantern_the_ambush", "lantern_choice_confrontation", "sequence", sequence_weight=80),
    EdgeSpec(
        "lantern_choice_confrontation",
        "lantern_lighting_the_old_lantern",
        "sequence",
        sequence_weight=95,
    ),
    EdgeSpec(
        "lantern_lighting_the_old_lantern", "lantern_debt_paid", "sequence", sequence_weight=100
    ),
    EdgeSpec("lantern_debt_paid", "lantern_epilogue_northpier", "sequence", sequence_weight=110),
    # Deliberate contradiction: an early draft belief the ambush was random chance,
    # contradicted once the guild's premeditation is revealed at lantern_saoirse_secret.
    EdgeSpec(
        "lantern_meets_saoirse",
        "lantern_the_ambush",
        "contradiction",
        label="Saoirse initially insists the guild has no idea where they're going",
    ),
    # A `custom` edge for a bespoke, app-specific relationship not covered by the
    # other four types.
    EdgeSpec(
        "lantern_the_old_wreck",
        "lantern_epilogue_northpier",
        "custom",
        label="mirrors: two lights, one keeper",
    ),
)

_VESPERS_EDGES = (
    EdgeSpec("vespers_ordinary_arcade", "vespers_call_signal", "sequence", sequence_weight=10),
    EdgeSpec("vespers_call_signal", "vespers_refusal_landlord", "sequence", sequence_weight=20),
    EdgeSpec(
        "vespers_refusal_landlord",
        "vespers_mentor_thale_jr",
        "causal",
        label="Kesh caves and asks for help",
    ),
    EdgeSpec(
        "vespers_mentor_thale_jr",
        "vespers_threshold_flooded_gate",
        "sequence",
        sequence_weight=40,
    ),
    EdgeSpec(
        "vespers_threshold_flooded_gate", "harbor_fog_intro", "reference", label="flashback cutaway"
    ),
    EdgeSpec("harbor_fog_intro", "vespers_ordeal_current", "sequence", sequence_weight=55),
    EdgeSpec("vespers_ordeal_current", "vespers_reward_source", "sequence", sequence_weight=60),
    EdgeSpec("vespers_reward_source", "vespers_return_district", "sequence", sequence_weight=70),
)

_SALT_EDGES = (
    EdgeSpec("salt_opening_kitchen", "salt_the_notice", "causal", label="notice arrives"),
    EdgeSpec("salt_the_notice", "salt_granddaughter_pushes", "sequence", sequence_weight=10),
    EdgeSpec("salt_granddaughter_pushes", "salt_final_harvest", "sequence", sequence_weight=20),
)

_LASTBUS_EDGES: tuple[EdgeSpec, ...] = ()  # single scene, nothing to connect


# ── Outline / Timeline ordering ──────────────────────────────────────────────
# FLASHBACK EDGE CASE (lantern): `lantern_wraith_shoal_arrival` and
# `lantern_the_old_wreck` are told in outline order right after the guildhall
# summons (chapter 2 opens on them), but in in-story chronology they actually
# happen years earlier — Saoirse's grandmother sealed that tower long before
# any of the present-day plot. `timeline_order_index` + `in_story_time_label`
# below push them to the front of the Timeline view even though they read
# later in the Outline/beat-board view. Every order row sets both fields so
# the Timeline tab visibly reorders relative to the Outline tab.
_LANTERN_ORDER = (
    OrderSpec("harbor_fog_intro", "lantern_ch1", 0, "Setup", 2, "Day 1 — dusk", 1.0),
    OrderSpec("lantern_opening_debt", "lantern_ch1", 1, "Setup", 3, "Day 1 — night", 1.5),
    OrderSpec(
        "lantern_guildhall_summons",
        "lantern_ch1",
        2,
        "Inciting Incident",
        4,
        "Day 2 — morning",
        2.0,
    ),
    OrderSpec(
        "lantern_meets_saoirse", "lantern_ch1", 3, "Inciting Incident", 5, "Day 2 — evening", 2.5
    ),
    OrderSpec(
        "lantern_first_argument", "lantern_ch2", 4, "Rising Action", 6, "Day 3 — at sea", 3.0
    ),
    # FLASHBACK: outline_order 5-6 come here narratively, but timeline_order
    # 0-1 place them decades earlier in the fabula.
    OrderSpec(
        "lantern_wraith_shoal_arrival",
        "lantern_ch2",
        5,
        "Rising Action",
        0,
        "Decades ago — the sealing",
        -20.0,
    ),
    OrderSpec(
        "lantern_the_old_wreck",
        "lantern_ch2",
        6,
        "Midpoint",
        1,
        "Decades ago — moments later",
        -19.5,
    ),
    OrderSpec("lantern_saoirse_secret", "lantern_ch2", 7, "Midpoint", 7, "Day 3 — night", 3.5),
    OrderSpec("lantern_the_ambush", "lantern_ch3", 8, "Climax", 8, "Day 4 — dawn", 4.0),
    OrderSpec(
        "lantern_choice_confrontation",
        "lantern_ch3",
        9,
        "Climax",
        9,
        "Day 4 — dawn, moments later",
        4.1,
    ),
    OrderSpec(
        "lantern_lighting_the_old_lantern",
        "lantern_ch3",
        10,
        "Falling Action",
        10,
        "Day 4 — full morning",
        4.5,
    ),
    OrderSpec("lantern_debt_paid", "lantern_ch3", 11, "Falling Action", 11, "Day 4 — noon", 5.0),
    OrderSpec(
        "lantern_epilogue_northpier", "lantern_ch3", 12, "Resolution", 12, "Weeks later", 20.0
    ),
)

_VESPERS_ORDER = (
    OrderSpec("vespers_ordinary_arcade", None, 0, "Ordinary World", 0, "Night 1", 1.0),
    OrderSpec("vespers_call_signal", None, 1, "Call to Adventure", 1, "Night 1", 1.1),
    OrderSpec("vespers_refusal_landlord", None, 2, "Refusal", 2, "Night 1", 1.2),
    OrderSpec("vespers_mentor_thale_jr", None, 3, "Meeting the Mentor", 3, "Night 2", 2.0),
    OrderSpec(
        "vespers_threshold_flooded_gate", None, 4, "Crossing the Threshold", 4, "Night 2", 2.1
    ),
    OrderSpec("harbor_fog_intro", None, 5, "Tests & Allies", 5, "Night 2 — flashback insert", 2.15),
    OrderSpec("vespers_ordeal_current", None, 6, "Ordeal", 6, "Night 2", 2.2),
    OrderSpec("vespers_reward_source", None, 7, "Reward", 7, "Night 2", 2.3),
    OrderSpec("vespers_return_district", None, 8, "Return with the Elixir", 8, "Night 3", 3.0),
)

_SALT_ORDER = (
    OrderSpec("salt_opening_kitchen", None, 0, "Setup", 0, "Day 1", 1.0),
    OrderSpec("salt_the_notice", None, 1, "Inciting Incident", 1, "Day 1", 1.1),
    OrderSpec("salt_granddaughter_pushes", None, 2, "Rising Action", 2, "Day 12", 2.0),
    # Deliberate mismatch: a beat name that matches NO Three-Act beat, so this
    # row should land in the BeatBoard's "Unassigned" lane.
    OrderSpec("salt_final_harvest", None, 3, "The Last Grain", 3, "Day 90", 3.0),
)

_LASTBUS_ORDER = (
    # Freeform template has no beats at all — structure_beat is None.
    OrderSpec("lastbus_only_scene", None, 0, None, 0, "2 a.m., forty years on", 1.0),
)


# ── Books ────────────────────────────────────────────────────────────────────
BOOKS: tuple[BookSpec, ...] = (
    BookSpec(
        key="lantern",
        title="The Lantern-Keeper's Debt",
        book_type="story_book",
        logline=(
            "When a dead man's debt threatens to take the only lighthouse she's ever loved, "
            "a lantern-keeper must hire the one smuggler who knows a path through a shoal "
            "that has swallowed every keeper who's tried it before — and discover that the "
            "debt was never about money at all."
        ),
        front_matter={
            "author": "Sample Library",
            "dedication": "For every keeper who lit the lamp anyway.",
            "genre": "Literary fantasy",
        },
        structure_template_name="Three-Act",
        cover_image_key="lantern_cover",
        chapters=_LANTERN_CHAPTERS,
        canvas=_LANTERN_CANVAS,
        edges=_LANTERN_EDGES,
        order=_LANTERN_ORDER,
    ),
    BookSpec(
        key="vespers",
        title="Neon Vespers",
        book_type="movie_script",
        logline=(
            "A rooftop drone mechanic who fixes other people's problems for a living finds "
            "a distress signal that shouldn't exist, and has to decide whether uncovering "
            "the guild secret buried under her own neighborhood is worth losing the small, "
            "safe life she built specifically to avoid this kind of trouble."
        ),
        front_matter={"author": "Sample Library", "genre": "Neo-noir sci-fi"},
        structure_template_name="Hero's Journey",
        cover_image_key="vespers_cover",
        chapters=(),
        canvas=_VESPERS_CANVAS,
        edges=_VESPERS_EDGES,
        order=_VESPERS_ORDER,
    ),
    BookSpec(
        key="salt",
        title="Salt",
        book_type="short_film_script",
        logline=(
            "On the last legal morning before a developer's notice takes her family's salt "
            "flats forever, an old salt-worker finally lets her granddaughter film the "
            "harvest — not to save it, but to be honest about what it always was."
        ),
        front_matter={"author": "Sample Library", "genre": "Quiet drama"},
        structure_template_name="Three-Act",
        cover_image_key="salt_cover",
        chapters=(),  # NO chapters, per spec
        canvas=_SALT_CANVAS,
        edges=_SALT_EDGES,
        order=_SALT_ORDER,
    ),
    BookSpec(
        key="lastbus",
        title="The Last Bus",
        book_type="single_scene",
        logline=(
            "Two strangers watch the last bus out of a dying neon district pull away without "
            "them, and choose, wordlessly, to stay a little longer than either of them meant "
            "to."
        ),
        front_matter={"author": "Sample Library", "genre": "Vignette"},
        structure_template_name="Freeform",
        cover_image_key="lastbus_cover",
        chapters=(),  # NO chapters, per spec
        canvas=_LASTBUS_CANVAS,
        edges=_LASTBUS_EDGES,
        order=_LASTBUS_ORDER,
    ),
)


# ── Codex entries (canonical, shared across Books) ─────────────────────────────
# `custom_fields` uses the frontend's MANAGED_KEYS ('role' for character, 'kind' for
# location/faction/object_lore, 'traits' for character) so the Codex dialog's guided
# Details-tab controls render them, per apps/desktop's codex-entry-dialog.tsx. Legal
# values come from apps/desktop/src/lib/vocab.ts's CHARACTER_ROLES/CHARACTER_TRAITS/
# LOCATION_KINDS/FACTION_KINDS/OBJECT_KINDS.
CODEX_ENTRIES: tuple[CodexSpec, ...] = (
    CodexSpec(
        key="mireille",
        entry_type="character",
        name="Mireille Ashgrove",
        summary=(
            "Northpier's keeper for six years, dutiful to a fault, inherited a debt she "
            "never agreed to and a tower she'd die before losing."
        ),
        # EDGE CASE: managed keys (role/traits) mixed with free-form keys (occupation/
        # voice/wants/fears/age) — the free-form ones surface in the dialog's separate
        # "Custom Fields" tab, giving that tab real content to render.
        custom_fields={
            "role": "protagonist",
            "traits": ["loyal", "stoic", "disciplined"],
            "age": 29,
            "occupation": "Lantern-keeper, Northpier",
            "voice": "clipped, precise, softens only around the lamp itself",
            "wants": "to keep Northpier lit without owing anyone anything for it",
            "fears": "becoming her father — dutiful right up until duty quietly ruins her",
        },
        portrait_image_key="mireille_portrait",
    ),
    CodexSpec(
        key="saoirse",
        entry_type="character",
        name="Saoirse Vane",
        summary=(
            "A smuggler who knows the harbor's unmarked water better than the guild's own "
            "charts, carrying a family secret about a drowned lantern tower."
        ),
        # EDGE CASE: managed + free-form mix (see mireille above).
        custom_fields={
            "role": "deuteragonist",
            "traits": ["cunning", "loyal", "reckless"],
            "age": 34,
            "occupation": "Smuggler",
            "voice": "wry, deflects with jokes, drops the act only when the shoal comes up",
        },
        # EDGE CASE: no portrait yet — deliberately left unset.
        portrait_image_key=None,
    ),
    CodexSpec(
        key="thale_sr",
        entry_type="character",
        name="Corvin Thale",
        summary=(
            "Guild-Master of the Lantern-Keepers' Guild, patient, procedural, and utterly "
            "convinced the ends justify however long the paperwork takes."
        ),
        custom_fields={"role": "antagonist", "traits": ["ambitious", "ruthless", "disciplined"]},
        portrait_image_key=None,
    ),
    CodexSpec(
        key="kesh",
        entry_type="character",
        name="Kesh Okonkwo-Lin",
        summary=(
            "A rooftop drone mechanic in the Vespers District who fixes other people's "
            "problems for a living and has spent years avoiding having any of her own."
        ),
        # EDGE CASE: managed + free-form mix (see mireille above) — third and last entry
        # deliberately covering the free-form "Custom Fields" tab.
        custom_fields={
            "role": "protagonist",
            "traits": ["cautious", "curious", "disciplined"],
            "age": 24,
            "occupation": "Drone mechanic",
            "voice": "deflects with technical jargon when nervous",
            "wants": "a quiet, unremarkable life nobody comes looking to disrupt",
            "fears": "being the kind of person things happen to, again",
        },
        portrait_image_key="kesh_portrait",
    ),
    CodexSpec(
        key="emeric",
        entry_type="character",
        name="Emeric Thale",
        summary=(
            "A pawn-shop owner and Corvin Thale's estranged grandson, who kept his "
            "grandfather's guild maps out of habit and now wishes he'd burned them."
        ),
        custom_fields={"role": "mentor", "traits": ["honest", "cautious"]},
        portrait_image_key=None,
    ),
    CodexSpec(
        key="ren",
        entry_type="character",
        name="Ren Okabe",
        summary=(
            "A salt-worker in her seventies whose family has worked the same flats since "
            "before the harbor had a proper name, quietly running out of mornings to do it."
        ),
        custom_fields={"role": "protagonist", "traits": ["stoic", "disciplined", "honest"]},
        portrait_image_key=None,
    ),
    CodexSpec(
        key="northpier_lighthouse",
        entry_type="location",
        name="Northpier Lighthouse",
        summary=(
            "A working lighthouse at the harbor's northern breakwater, kept by the Ashgrove "
            "family for two generations."
        ),
        custom_fields={"kind": "building"},
        portrait_image_key=None,
    ),
    CodexSpec(
        key="wraith_shoal",
        entry_type="location",
        name="Wraith Shoal",
        summary=(
            "A treacherous rock shoal past the breakwater, said to have swallowed every "
            "keeper who tried to chart it — home to a drowned lantern tower far older than "
            "the guild."
        ),
        custom_fields={"kind": "wilderness"},
        portrait_image_key=None,
    ),
    CodexSpec(
        key="vespers_district",
        entry_type="location",
        name="Vespers District",
        summary=(
            "A flooded-neon nightlife district built directly atop the old lantern guild's "
            "abandoned lower level, decades after electricity made the guild's original "
            "purpose obsolete."
        ),
        custom_fields={"kind": "region"},
        portrait_image_key=None,
    ),
    CodexSpec(
        key="lantern_guild",
        entry_type="faction",
        name="The Lantern-Keepers' Guild",
        summary=(
            "A once-essential maritime guild, now largely ceremonial, still quietly "
            "protective of its oldest and most inconvenient secrets."
        ),
        custom_fields={"kind": "guild"},
        portrait_image_key=None,
    ),
    CodexSpec(
        key="salt_flats_co",
        entry_type="faction",
        name="Harborline Development Group",
        summary=(
            "The development company that purchased Ren's salt flats out from under her "
            "with a ninety-day notice and a waterfront condo rendering."
        ),
        # EDGE CASE: custom_fields entirely unset (None) — the Codex dialog should show
        # no managed value and an empty Custom Fields tab for this entry.
        custom_fields=None,
        portrait_image_key=None,
    ),
    CodexSpec(
        key="grandmothers_seal",
        entry_type="object_lore",
        name="The Sealing of the Drowned Tower",
        summary=(
            "The act — and the guild-suppressed story of it — by which a Northpier keeper "
            "a generation before Mireille's father sealed the original lantern tower under "
            "Wraith Shoal rather than let the guild misuse its light."
        ),
        custom_fields={"kind": "relic"},
        portrait_image_key=None,
    ),
)


# ── Codex ↔ Book cast links ──────────────────────────────────────────────────
CODEX_BOOK_LINKS: tuple[CodexBookLinkSpec, ...] = (
    CodexBookLinkSpec("mireille", "lantern", role_note="Protagonist"),
    CodexBookLinkSpec("saoirse", "lantern", role_note="Deuteragonist / love interest"),
    CodexBookLinkSpec("thale_sr", "lantern", role_note="Antagonist"),
    CodexBookLinkSpec("northpier_lighthouse", "lantern", role_note="Primary setting"),
    CodexBookLinkSpec("wraith_shoal", "lantern", role_note="Primary setting"),
    CodexBookLinkSpec("lantern_guild", "lantern", role_note="Antagonist faction"),
    CodexBookLinkSpec("grandmothers_seal", "lantern", role_note="Central mystery object"),
    # EDGE CASE: Corvin Thale is cast in BOTH `lantern` (as antagonist) and
    # `vespers` (as an off-screen mentioned figure via his grandson's arc) —
    # one canonical character belonging to two Books' casts at once.
    CodexBookLinkSpec(
        "thale_sr", "vespers", role_note="Referenced off-screen; grandfather to Emeric"
    ),
    CodexBookLinkSpec("kesh", "vespers", role_note="Protagonist"),
    CodexBookLinkSpec("emeric", "vespers", role_note="Mentor"),
    CodexBookLinkSpec("vespers_district", "vespers", role_note="Primary setting"),
    CodexBookLinkSpec("lantern_guild", "vespers", role_note="Background antagonist faction"),
    CodexBookLinkSpec("ren", "salt", role_note="Protagonist"),
    CodexBookLinkSpec("salt_flats_co", "salt", role_note="Antagonist faction"),
)

CODEX_SCENE_LINKS: tuple[CodexSceneLinkSpec, ...] = (
    CodexSceneLinkSpec("mireille", "lantern_opening_debt", note="POV"),
    CodexSceneLinkSpec("mireille", "harbor_fog_intro", note="POV, shared scene"),
    CodexSceneLinkSpec("thale_sr", "lantern_guildhall_summons", note="delivers the ultimatum"),
    CodexSceneLinkSpec("saoirse", "lantern_meets_saoirse", note="introduced"),
    CodexSceneLinkSpec("saoirse", "lantern_saoirse_secret", note="reveal"),
    CodexSceneLinkSpec("northpier_lighthouse", "lantern_opening_debt", note="setting"),
    CodexSceneLinkSpec("wraith_shoal", "lantern_the_old_wreck", note="setting"),
    CodexSceneLinkSpec("kesh", "vespers_ordinary_arcade", note="POV"),
    CodexSceneLinkSpec("kesh", "harbor_fog_intro", note="flashback POV, shared scene"),
    CodexSceneLinkSpec("emeric", "vespers_mentor_thale_jr", note="introduced"),
    CodexSceneLinkSpec("vespers_district", "vespers_ordinary_arcade", note="setting"),
    CodexSceneLinkSpec("ren", "salt_opening_kitchen", note="POV"),
    CodexSceneLinkSpec("ren", "salt_final_harvest", note="POV"),
)


# ── Relationships — a connected graph, not a star (≥4 edges) ──────────────────
# `relationship_type` normally uses RELATIONSHIP_TYPES (apps/desktop/src/lib/vocab.ts)
# values, but the column carries no CHECK constraint, so one row below deliberately
# uses a free-text value outside that list as an edge case.
RELATIONSHIPS: tuple[RelationshipSpec, ...] = (
    RelationshipSpec(
        "mireille",
        "saoirse",
        "romantic",
        "Hired her out of necessity; ends up trusting her completely.",
    ),
    RelationshipSpec(
        "saoirse",
        "thale_sr",
        "enemy",
        "Her grandmother's secret is the exact thing his guild wants back.",
    ),
    RelationshipSpec("mireille", "thale_sr", "enemy", "He holds her father's debt over her head."),
    RelationshipSpec(
        "thale_sr",
        "emeric",
        "family",
        "Estranged grandfather; Emeric wants nothing to do with the guild.",
    ),
    RelationshipSpec(
        "emeric", "kesh", "mentor", "Recognizes the signal and helps her investigate."
    ),
    # EDGE CASE: free-text relationship_type outside RELATIONSHIP_TYPES — legal because
    # `codex_relationships.relationship_type` has no DB CHECK constraint.
    RelationshipSpec(
        "mireille",
        "grandmothers_seal",
        "unspoken_bond",
        "Inherits the responsibility Saoirse's grandmother once carried, unnamed by any formal "
        "relation.",
    ),
)


# ── Arc states — ≥2 at different outline positions ─────────────────────────────
ARC_STATES: tuple[ArcStateSpec, ...] = (
    ArcStateSpec(
        codex_key="mireille",
        book_key="lantern",
        as_of_outline_order_index=1,
        status_summary="Dutiful, cornered, still believes the debt is only about money.",
        traits_snapshot={"resolve": "reluctant", "trust_in_guild": "eroding"},
    ),
    ArcStateSpec(
        codex_key="mireille",
        book_key="lantern",
        as_of_outline_order_index=12,
        status_summary="Has chosen Saoirse and the truth over the guild's version of duty.",
        traits_snapshot={"resolve": "resolute", "trust_in_guild": "none"},
    ),
    ArcStateSpec(
        codex_key="kesh",
        book_key="vespers",
        as_of_outline_order_index=0,
        status_summary="Deliberately small life, avoids anything that could disrupt it.",
        traits_snapshot={"risk_tolerance": "low"},
    ),
    ArcStateSpec(
        codex_key="kesh",
        book_key="vespers",
        as_of_outline_order_index=8,
        status_summary="Carrying proof of a secret bigger than she wanted, and staying anyway.",
        traits_snapshot={"risk_tolerance": "high"},
    ),
)


# ── Images ───────────────────────────────────────────────────────────────────
IMAGES: tuple[ImageSpec, ...] = (
    ImageSpec(
        key="lantern_cover",
        kind="cover",
        bucket="finalized_scene",
        display_name="The Lantern-Keeper's Debt — Cover",
        description="A single lantern glowing through harbor fog at dusk.",
        tags=("cover", "harbor", "lantern"),
        seed="lantern-cover-01",
    ),
    ImageSpec(
        key="mireille_portrait",
        kind="portrait",
        bucket="reference_pool",
        display_name="Mireille Ashgrove — Portrait",
        description="Windswept, practical coat, a keeper's lamp-oil stains on her cuffs.",
        tags=("character", "portrait"),
        seed="mireille-portrait-01",
    ),
    ImageSpec(
        key="kesh_portrait",
        kind="portrait",
        bucket="reference_pool",
        display_name="Kesh Okonkwo-Lin — Portrait",
        description="Rooftop-tan, tool harness, a drone perched on one shoulder.",
        tags=("character", "portrait"),
        seed="kesh-portrait-01",
    ),
    ImageSpec(
        key="wreck_scene_art",
        kind="scene",
        bucket="finalized_scene",
        display_name="The Old Wreck — Scene Art",
        description="A drowned lantern tower half-swallowed by coral and silt.",
        tags=(),  # EDGE CASE: deliberately empty tags
        seed="wreck-scene-01",
    ),
    # EDGE CASE: second image on the SAME scene (`lantern_the_old_wreck`) as
    # `wreck_scene_art` above, attached with order_index=1 (wreck_scene_art is
    # order_index=0 in ENTITY_IMAGES below) — exercises the thumbnail-strip
    # multi-image ordering path.
    ImageSpec(
        key="wreck_closeup_art",
        kind="scene",
        bucket="finalized_scene",
        display_name="The Old Wreck — Lens Chamber Close-Up",
        description="Barnacle-crusted lens housing, faint warmth still visible under the grime.",
        tags=("scene", "harbor", "lantern"),
        seed="wreck-closeup-01",
    ),
    ImageSpec(
        key="vespers_cover",
        kind="cover",
        bucket="finalized_scene",
        display_name="Neon Vespers — Cover",
        description="Rain-slicked rooftop antennas against a flooded-neon skyline.",
        tags=("cover", "neon", "vespers"),
        seed="vespers-cover-01",
    ),
    ImageSpec(
        key="salt_cover",
        kind="cover",
        bucket="finalized_scene",
        display_name="Salt — Cover",
        description="White salt-pan rows steaming under a harbor sunrise.",
        tags=("cover", "harbor", "salt"),
        seed="salt-cover-01",
    ),
    ImageSpec(
        key="lastbus_cover",
        kind="cover",
        bucket="finalized_scene",
        display_name="The Last Bus — Cover",
        description="A single lantern-shaped streetlamp over a flooded curb at 2 a.m.",
        tags=("cover", "neon", "vespers"),
        seed="lastbus-cover-01",
    ),
    ImageSpec(
        key="guildhall_scene_art",
        kind="scene",
        bucket="finalized_scene",
        display_name="The Guildhall — Scene Art",
        description="Brass and whale-oil-scented logbooks lining a two-hundred-year-old study.",
        tags=("scene", "harbor", "lantern"),
        seed="guildhall-scene-01",
    ),
    ImageSpec(
        key="ambush_scene_art",
        kind="scene",
        bucket="finalized_scene",
        display_name="The Ambush — Scene Art",
        description="Guild skiffs closing in out of the fog, running lights doused.",
        tags=("scene", "harbor", "action"),
        seed="ambush-scene-01",
    ),
    ImageSpec(
        key="vespers_gate_scene_art",
        kind="scene",
        bucket="finalized_scene",
        display_name="The Flood Gate — Scene Art",
        description="A forty-year-sealed flood gate groaning open onto a faintly lit corridor.",
        tags=("scene", "vespers", "neon"),
        seed="vespers-gate-scene-01",
    ),
    ImageSpec(
        key="vespers_reward_scene_art",
        kind="scene",
        bucket="finalized_scene",
        display_name="The Second Lantern — Scene Art",
        description="A second sealed lantern mechanism, identical to the one at Wraith Shoal.",
        tags=("scene", "vespers", "lantern"),
        seed="vespers-reward-scene-01",
    ),
    # Codex moodboards — reference_pool images attached to a location and an
    # object_lore entry, rather than only characters getting portraits.
    ImageSpec(
        key="wraith_shoal_moodboard",
        kind="scene",
        bucket="reference_pool",
        display_name="Wraith Shoal — Moodboard",
        description="Rocks worn into shapes that almost resemble hands reaching from the water.",
        tags=("moodboard", "location", "harbor"),
        seed="wraith-shoal-moodboard-01",
    ),
    ImageSpec(
        key="grandmothers_seal_moodboard",
        kind="scene",
        bucket="reference_pool",
        display_name="The Sealing of the Drowned Tower — Moodboard",
        description="Reference collage for the guild-suppressed sealing story.",
        tags=("moodboard", "lore", "lantern"),
        seed="grandmothers-seal-moodboard-01",
    ),
)

ENTITY_IMAGES: tuple[EntityImageSpec, ...] = (
    EntityImageSpec("lantern_cover", "book", "lantern", role="cover", order_index=0),
    EntityImageSpec("mireille_portrait", "codex_entry", "mireille", role="portrait", order_index=0),
    EntityImageSpec("kesh_portrait", "codex_entry", "kesh", role="portrait", order_index=0),
    # EDGE CASE: two images on the same scene, ordered 0 then 1 — thumbnail-strip
    # multi-image ordering coverage.
    EntityImageSpec(
        "wreck_scene_art", "scene", "lantern_the_old_wreck", role="reference", order_index=0
    ),
    EntityImageSpec(
        "wreck_closeup_art", "scene", "lantern_the_old_wreck", role="reference", order_index=1
    ),
    EntityImageSpec("vespers_cover", "book", "vespers", role="cover", order_index=0),
    EntityImageSpec("salt_cover", "book", "salt", role="cover", order_index=0),
    EntityImageSpec("lastbus_cover", "book", "lastbus", role="cover", order_index=0),
    EntityImageSpec(
        "guildhall_scene_art", "scene", "lantern_guildhall_summons", role="reference", order_index=0
    ),
    EntityImageSpec(
        "ambush_scene_art", "scene", "lantern_the_ambush", role="reference", order_index=0
    ),
    EntityImageSpec(
        "vespers_gate_scene_art",
        "scene",
        "vespers_threshold_flooded_gate",
        role="reference",
        order_index=0,
    ),
    EntityImageSpec(
        "vespers_reward_scene_art",
        "scene",
        "vespers_reward_source",
        role="reference",
        order_index=0,
    ),
    # Codex moodboards on a location and an object_lore entry (not just characters).
    EntityImageSpec(
        "wraith_shoal_moodboard", "codex_entry", "wraith_shoal", role="moodboard", order_index=0
    ),
    EntityImageSpec(
        "grandmothers_seal_moodboard",
        "codex_entry",
        "grandmothers_seal",
        role="moodboard",
        order_index=0,
    ),
)


# ── Continuity flags — full coverage of flag_type / severity / status / source ──
CONTINUITY_FLAGS: tuple[ContinuityFlagSpec, ...] = (
    ContinuityFlagSpec(
        book_key="lantern",
        scene_key="lantern_saoirse_secret",
        codex_key="saoirse",
        flag_type="early_appearance",
        severity="warning",
        description=(
            "Saoirse's grandmother is referenced before any earlier scene establishes she exists."
        ),
        status="open",
        source="deterministic",
    ),
    ContinuityFlagSpec(
        book_key="lantern",
        scene_key="lantern_the_ambush",
        codex_key="thale_sr",
        flag_type="trait_contradiction",
        severity="critical",
        description=(
            "Thale is characterized as strictly procedural earlier, but here ambushes "
            "without paperwork or warning."
        ),
        status="open",
        source="ai",
    ),
    ContinuityFlagSpec(
        book_key="lantern",
        scene_key="lantern_wraith_shoal_arrival",
        codex_key=None,
        flag_type="timeline_conflict",
        severity="hint",
        description=(
            "Flashback beat's in-story time predates the frame story by decades — "
            "confirm this is intentional (it is)."
        ),
        status="dismissed",
        source="manual",
    ),
    ContinuityFlagSpec(
        book_key="vespers",
        scene_key="vespers_mentor_thale_jr",
        codex_key="emeric",
        flag_type="custom",
        severity="warning",
        description=(
            "Emeric recognizes a retired guild frequency instantly with no prior scene "
            "establishing his guild knowledge."
        ),
        status="resolved",
        source="manual",
    ),
    ContinuityFlagSpec(
        book_key="salt",
        scene_key=None,
        codex_key="ren",
        flag_type="trait_contradiction",
        severity="hint",
        description=(
            "Ren is described as allergic to speeches, but the final harvest scene gives "
            "her an extended internal monologue."
        ),
        status="open",
        source="deterministic",
    ),
)


# ── Scene revision chains — full coverage of change_source ─────────────────────
REVISIONS: tuple[RevisionSpec, ...] = (
    RevisionSpec(
        scene_key="lantern_lighting_the_old_lantern",
        revision_number=1,
        title="Lighting the Drowned Lantern",
        description="Draft placeholder: she lights it, something happens, TBD.",
        status="draft",
        change_source="manual_edit",
        note="First pass, needs real prose.",
    ),
    RevisionSpec(
        scene_key="lantern_lighting_the_old_lantern",
        revision_number=2,
        title="Lighting the Drowned Lantern",
        description=(
            "She strikes the flint against the old lens housing and for one long second "
            "nothing happens at all, long enough to believe the whole shoal was only ever "
            "a story."
        ),
        status="revised",
        change_source="enhance_accept",
        note="Accepted an Enhance pass for pacing.",
    ),
    RevisionSpec(
        scene_key="lantern_lighting_the_old_lantern",
        revision_number=3,
        title="Lighting the Drowned Lantern",
        description=None,
        status="revised",
        change_source="ai_merge",
        note="Merged with a discarded alternate take on the same beat.",
    ),
    RevisionSpec(
        scene_key="lantern_lighting_the_old_lantern",
        revision_number=4,
        title="Lighting the Drowned Lantern",
        description="Draft placeholder: she lights it, something happens, TBD.",
        status="draft",
        change_source="restore",
        note="Restored revision 1 after deciding the merge lost the right tone.",
    ),
)


# ── Self-validation ─────────────────────────────────────────────────────────
def _validate() -> None:
    """Fail fast and loudly on any internal inconsistency in this sample data."""
    errors: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    # No duplicate keys.
    def _dupes(keys: list[str]) -> list[str]:
        seen: set[str] = set()
        dupes: list[str] = []
        for k in keys:
            if k in seen:
                dupes.append(k)
            seen.add(k)
        return dupes

    check(
        not _dupes([s.key for s in SCENES]),
        f"duplicate scene keys: {_dupes([s.key for s in SCENES])}",
    )
    check(
        not _dupes([c.key for c in CODEX_ENTRIES]),
        f"duplicate codex keys: {_dupes([c.key for c in CODEX_ENTRIES])}",
    )
    check(
        not _dupes([b.key for b in BOOKS]), f"duplicate book keys: {_dupes([b.key for b in BOOKS])}"
    )
    check(
        not _dupes([i.key for i in IMAGES]),
        f"duplicate image keys: {_dupes([i.key for i in IMAGES])}",
    )
    for book in BOOKS:
        check(
            not _dupes([c.key for c in book.chapters]),
            f"{book.key}: duplicate chapter keys",
        )

    scene_keys = {s.key for s in SCENES}
    codex_keys = {c.key for c in CODEX_ENTRIES}
    book_keys = {b.key for b in BOOKS}
    image_keys = {i.key for i in IMAGES}

    # Enum coverage / legality checks.
    for s in SCENES:
        check(s.node_type in _NODE_TYPES, f"scene {s.key}: illegal node_type {s.node_type!r}")
        check(s.status in _STATUSES, f"scene {s.key}: illegal status {s.status!r}")

    for b in BOOKS:
        check(b.book_type in _BOOK_TYPES, f"book {b.key}: illegal book_type {b.book_type!r}")
        check(
            b.structure_template_name in _STRUCTURE_TEMPLATE_NAMES,
            f"book {b.key}: illegal structure_template_name {b.structure_template_name!r}",
        )
        if b.cover_image_key is not None:
            check(
                b.cover_image_key in image_keys,
                f"book {b.key}: cover_image_key {b.cover_image_key!r} not in IMAGES",
            )

        canvas_scene_keys = {n.scene_key for n in b.canvas}
        for n in b.canvas:
            check(
                n.scene_key in scene_keys,
                f"book {b.key}: canvas references unknown scene {n.scene_key!r}",
            )

        chapter_keys = {c.key for c in b.chapters}
        for e in b.edges:
            check(
                e.source_key in canvas_scene_keys,
                f"book {b.key}: edge source {e.source_key!r} not on canvas",
            )
            check(
                e.target_key in canvas_scene_keys,
                f"book {b.key}: edge target {e.target_key!r} not on canvas",
            )
            check(
                e.connection_type in _CONNECTION_TYPES,
                f"book {b.key}: illegal connection_type {e.connection_type!r}",
            )

        for o in b.order:
            check(
                o.scene_key in canvas_scene_keys,
                f"book {b.key}: order row scene {o.scene_key!r} is not on that book's canvas",
            )
            if o.chapter_key is not None:
                check(
                    o.chapter_key in chapter_keys,
                    f"book {b.key}: order row references unknown chapter {o.chapter_key!r}",
                )

    for el in SCREENPLAY_ELEMENTS:
        check(
            el.scene_key in scene_keys,
            f"screenplay element references unknown scene {el.scene_key!r}",
        )
        check(el.element_type in _ELEMENT_TYPES, f"illegal element_type {el.element_type!r}")

    for c in CODEX_ENTRIES:
        check(c.entry_type in _ENTRY_TYPES, f"codex {c.key}: illegal entry_type {c.entry_type!r}")
        if c.portrait_image_key is not None:
            check(
                c.portrait_image_key in image_keys,
                f"codex {c.key}: portrait_image_key {c.portrait_image_key!r} not in IMAGES",
            )

    for link in CODEX_BOOK_LINKS:
        check(link.codex_key in codex_keys, f"codex_book_link: unknown codex {link.codex_key!r}")
        check(link.book_key in book_keys, f"codex_book_link: unknown book {link.book_key!r}")

    for link in CODEX_SCENE_LINKS:
        check(link.codex_key in codex_keys, f"codex_scene_link: unknown codex {link.codex_key!r}")
        check(link.scene_key in scene_keys, f"codex_scene_link: unknown scene {link.scene_key!r}")

    for rel in RELATIONSHIPS:
        check(rel.from_key in codex_keys, f"relationship: unknown from_key {rel.from_key!r}")
        check(rel.to_key in codex_keys, f"relationship: unknown to_key {rel.to_key!r}")

    for arc in ARC_STATES:
        check(arc.codex_key in codex_keys, f"arc_state: unknown codex {arc.codex_key!r}")
        check(arc.book_key in book_keys, f"arc_state: unknown book {arc.book_key!r}")

    for img in IMAGES:
        check(img.kind in _IMAGE_KINDS, f"image {img.key}: illegal kind {img.kind!r}")
        check(img.bucket in _BUCKETS, f"image {img.key}: illegal bucket {img.bucket!r}")

    for ei in ENTITY_IMAGES:
        check(ei.image_key in image_keys, f"entity_image: unknown image {ei.image_key!r}")
        check(
            ei.entity_type in _ENTITY_TYPES, f"entity_image: illegal entity_type {ei.entity_type!r}"
        )
        if ei.entity_type == "book":
            check(ei.entity_key in book_keys, f"entity_image: unknown book {ei.entity_key!r}")
        elif ei.entity_type == "scene":
            check(ei.entity_key in scene_keys, f"entity_image: unknown scene {ei.entity_key!r}")
        elif ei.entity_type == "codex_entry":
            check(
                ei.entity_key in codex_keys, f"entity_image: unknown codex entry {ei.entity_key!r}"
            )

    for flag in CONTINUITY_FLAGS:
        check(flag.book_key in book_keys, f"continuity_flag: unknown book {flag.book_key!r}")
        if flag.scene_key is not None:
            check(
                flag.scene_key in scene_keys, f"continuity_flag: unknown scene {flag.scene_key!r}"
            )
        if flag.codex_key is not None:
            check(
                flag.codex_key in codex_keys, f"continuity_flag: unknown codex {flag.codex_key!r}"
            )
        check(
            flag.flag_type in _FLAG_TYPES, f"continuity_flag: illegal flag_type {flag.flag_type!r}"
        )
        check(flag.severity in _SEVERITIES, f"continuity_flag: illegal severity {flag.severity!r}")
        check(flag.status in _FLAG_STATUSES, f"continuity_flag: illegal status {flag.status!r}")
        check(flag.source in _FLAG_SOURCES, f"continuity_flag: illegal source {flag.source!r}")

    for rev in REVISIONS:
        check(rev.scene_key in scene_keys, f"revision: unknown scene {rev.scene_key!r}")
        check(
            rev.change_source in _CHANGE_SOURCES,
            f"revision {rev.scene_key}#{rev.revision_number}: "
            f"illegal change_source {rev.change_source!r}",
        )

    if errors:
        raise ValueError(
            "sample_library.content failed validation:\n" + "\n".join(f"- {e}" for e in errors)
        )


_validate()
