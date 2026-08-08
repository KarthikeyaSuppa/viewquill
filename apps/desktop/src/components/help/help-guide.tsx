import { useState, type ReactNode } from 'react'
import {
  BookOpen,
  Check,
  Compass,
  HelpCircle,
  Keyboard,
  Lightbulb,
  Map,
  ScrollText,
  Sparkles,
  Users,
  X,
} from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { ScrollHighlight } from '@/components/ui/scroll-highlight'
import { cn } from '@/lib/utils'
import { useDelight } from '@/lib/delight'

/** The three node-type accent colors, pulled out of `components/canvas/nodes.tsx`'s
 * `accentClass` values (`bg-[oklch(...)]`) as plain color strings — that file's own
 * `accentColorFromClass` helper does the same extraction for the canvas's real handle
 * dots, but isn't exported, so this is a small deliberate duplicate rather than a new
 * import coupling this static help content to the live canvas node module. Keep these
 * three in sync with `nodes.tsx` if that file's accents ever change. */
const ACCENT_SCENE = 'oklch(0.54 0.21 277)'
const ACCENT_PLOT_POINT = 'oklch(0.7 0.16 55)'
const ACCENT_THOUGHT = 'oklch(0.6 0.13 195)'

/** A short, bordered example box — used throughout the guide to show one concrete,
 * concrete-numbers workflow rather than another paragraph of prose (dyslexia-friendly:
 * short lines, plain language, visually set apart from the surrounding text). */
function Example({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-primary/25 bg-primary/5 p-3 text-sm">
      <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-primary">
        <Sparkles className="size-3.5" />
        Example
      </p>
      {children}
    </div>
  )
}

function H3({ children }: { children: ReactNode }) {
  return <h3 className="text-sm font-semibold tracking-tight">{children}</h3>
}

function P({ children }: { children: ReactNode }) {
  return <p className="text-sm leading-relaxed text-muted-foreground">{children}</p>
}

/** A real keycap, not a plain text badge — `<kbd>` is the semantically-correct element
 * for "this is a key you press", and reads clearly at a glance against the bordered
 * `bg-muted` treatment used for every shortcut in this guide. */
function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex min-w-7 shrink-0 items-center justify-center rounded-md border border-border bg-muted px-1.5 py-0.5 font-mono text-[11px] font-medium text-foreground">
      {children}
    </kbd>
  )
}

/**
 * CANVAS diagram — three node cards (Scene / Plot point / Thought), each with the same
 * anatomy the real canvas card has (accent top strip, an image-placeholder rect, a
 * caption) plus small handle dots on their side edges, linked left-to-right by two
 * bowed connector curves with arrowheads. Every color is a theme CSS var except the
 * three accent strips (`ACCENT_*` above) — those are the same fixed per-node-type
 * colors in both Day and Night, exactly like the real canvas.
 */
function CanvasDiagram() {
  const y = 34
  const w = 150
  const h = 112
  const cards = [
    { x: 10, accent: ACCENT_SCENE, label: 'Scene', caption: 'a real story beat' },
    { x: 205, accent: ACCENT_PLOT_POINT, label: 'Plot point', caption: 'needs to happen' },
    { x: 400, accent: ACCENT_THOUGHT, label: 'Thought', caption: 'a loose idea' },
  ]

  return (
    <svg
      viewBox="0 0 560 180"
      className="h-auto w-full"
      role="img"
      aria-label="Diagram: Scene, Plot point, and Thought node cards connected left to right by curved lines"
      style={{ fontFamily: 'inherit' }}
    >
      <title>Scene, Plot point, and Thought nodes connected by curved links</title>
      <defs>
        <marker
          id="help-canvas-arrow"
          viewBox="0 0 8 8"
          refX="6"
          refY="4"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L8,4 L0,8 Z" fill="var(--muted-foreground)" />
        </marker>
      </defs>

      {/* connectors first, so the cards sit visually on top of the lines */}
      <path
        d="M160,90 C180,64 185,116 205,90"
        fill="none"
        stroke="var(--muted-foreground)"
        strokeWidth="1.5"
        markerEnd="url(#help-canvas-arrow)"
      />
      <path
        d="M355,90 C375,64 380,116 400,90"
        fill="none"
        stroke="var(--muted-foreground)"
        strokeWidth="1.5"
        markerEnd="url(#help-canvas-arrow)"
      />

      {cards.map((card) => (
        <g key={card.label}>
          <rect x={card.x} y={y} width={w} height={h} rx={12} fill="var(--card)" stroke="var(--border)" />
          <rect x={card.x} y={y} width={w} height={6} rx={3} fill={card.accent} />
          <text x={card.x + 12} y={y + 24} fontSize="10" fontWeight={600} fill="var(--foreground)">
            {card.label}
          </text>
          <rect
            x={card.x + 12}
            y={y + 32}
            width={w - 24}
            height={38}
            rx={8}
            fill="none"
            stroke="var(--border)"
            strokeDasharray="3 3"
          />
          <text x={card.x + 12} y={y + 90} fontSize="8.5" fill="var(--muted-foreground)">
            {card.caption}
          </text>
          {/* handle dots, same left/right connection points the real canvas card has */}
          <circle
            cx={card.x}
            cy={y + h / 2}
            r={4}
            fill="var(--background)"
            stroke="var(--muted-foreground)"
            strokeWidth="1.5"
          />
          <circle
            cx={card.x + w}
            cy={y + h / 2}
            r={4}
            fill="var(--background)"
            stroke="var(--muted-foreground)"
            strokeWidth="1.5"
          />
        </g>
      ))}
    </svg>
  )
}

/** GETTING STARTED diagram — the 3-stop shape of the whole app: Book → Canvas → Draft. */
function GettingStartedFlow() {
  const steps = [
    { label: 'Book', caption: 'start in the Library' },
    { label: 'Canvas', caption: 'add nodes, write' },
    { label: 'Draft', caption: 'arrange & compile' },
  ]
  const boxW = 130
  const boxH = 56
  const gap = 35
  const y = 12

  return (
    <svg
      viewBox="0 0 500 80"
      className="h-auto w-full max-w-md"
      role="img"
      aria-label="Diagram: Book leads to Canvas leads to Draft"
      style={{ fontFamily: 'inherit' }}
    >
      <title>Book, then Canvas, then Draft</title>
      <defs>
        <marker
          id="help-getting-started-arrow"
          viewBox="0 0 8 8"
          refX="6"
          refY="4"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L8,4 L0,8 Z" fill="var(--muted-foreground)" />
        </marker>
      </defs>
      {steps.map((step, index) => {
        const x = index * (boxW + gap) + 10
        return (
          <g key={step.label}>
            {index > 0 && (
              <line
                x1={x - gap + 4}
                y1={y + boxH / 2}
                x2={x - 4}
                y2={y + boxH / 2}
                stroke="var(--muted-foreground)"
                strokeWidth="1.5"
                markerEnd="url(#help-getting-started-arrow)"
              />
            )}
            <rect x={x} y={y} width={boxW} height={boxH} rx={10} fill="var(--card)" stroke="var(--border)" />
            <text
              x={x + boxW / 2}
              y={y + 26}
              textAnchor="middle"
              fontSize="12"
              fontWeight={600}
              fill="var(--foreground)"
            >
              {step.label}
            </text>
            <text
              x={x + boxW / 2}
              y={y + 42}
              textAnchor="middle"
              fontSize="8.5"
              fill="var(--muted-foreground)"
            >
              {step.caption}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

/**
 * CODEX diagram — a character card linked to a scene node (shows "link a character to
 * a scene"), plus a tiny 3-node relationship triad with curved edges, echoing the
 * Codex's own relationship map (`character-relationship-graph.tsx`).
 */
function CodexDiagram() {
  const triad = {
    a: { x: 400, y: 30 },
    b: { x: 520, y: 30 },
    c: { x: 460, y: 105 },
  }

  return (
    <svg
      viewBox="0 0 560 150"
      className="h-auto w-full"
      role="img"
      aria-label="Diagram: a character entry linked to a scene, and three codex entries connected in a relationship triad"
      style={{ fontFamily: 'inherit' }}
    >
      <title>Linking a character to a scene, and a relationship triad</title>
      <defs>
        <marker
          id="help-codex-arrow"
          viewBox="0 0 8 8"
          refX="6"
          refY="4"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L8,4 L0,8 Z" fill="var(--muted-foreground)" />
        </marker>
      </defs>

      {/* character card, linked to a scene node */}
      <rect x={10} y={35} width={130} height={80} rx={12} fill="var(--card)" stroke="var(--border)" />
      <circle cx={38} cy={62} r={12} fill="none" stroke="var(--primary)" strokeWidth="1.5" />
      <text x={38} y={66} textAnchor="middle" fontSize="10" fontWeight={600} fill="var(--primary)">
        K
      </text>
      <text x={60} y={58} fontSize="10" fontWeight={600} fill="var(--foreground)">
        Kael
      </text>
      <text x={60} y={72} fontSize="8" fill="var(--muted-foreground)">
        Character
      </text>
      <text x={20} y={104} fontSize="8" fill="var(--muted-foreground)">
        linked to a scene →
      </text>

      <line
        x1={140}
        y1={75}
        x2={195}
        y2={75}
        stroke="var(--muted-foreground)"
        strokeWidth="1.5"
        strokeDasharray="3 3"
        markerEnd="url(#help-codex-arrow)"
      />

      <rect x={200} y={45} width={90} height={60} rx={10} fill="var(--card)" stroke="var(--border)" />
      <rect x={200} y={45} width={90} height={5} rx={2.5} fill={ACCENT_SCENE} />
      <text x={210} y={70} fontSize="9" fontWeight={600} fill="var(--foreground)">
        Arrival
      </text>
      <text x={210} y={84} fontSize="7.5" fill="var(--muted-foreground)">
        Scene
      </text>

      {/* relationship triad, echoing the Codex's own relationship map */}
      <path
        d={`M${triad.a.x},${triad.a.y} C${triad.a.x + 40},${triad.a.y - 15} ${triad.b.x - 40},${triad.b.y - 15} ${triad.b.x},${triad.b.y}`}
        fill="none"
        stroke="var(--muted-foreground)"
        strokeWidth="1.3"
      />
      <path
        d={`M${triad.b.x},${triad.b.y} C${triad.b.x - 20},${triad.c.y - 25} ${triad.c.x + 20},${triad.c.y - 5} ${triad.c.x},${triad.c.y}`}
        fill="none"
        stroke="var(--muted-foreground)"
        strokeWidth="1.3"
      />
      <path
        d={`M${triad.c.x},${triad.c.y} C${triad.c.x - 20},${triad.a.y - 5} ${triad.a.x + 20},${triad.a.y - 25} ${triad.a.x},${triad.a.y}`}
        fill="none"
        stroke="var(--muted-foreground)"
        strokeWidth="1.3"
      />
      {[triad.a, triad.b, triad.c].map((point, index) => (
        <circle
          key={index}
          cx={point.x}
          cy={point.y}
          r={9}
          fill="var(--primary)"
          fillOpacity={0.15}
          stroke="var(--primary)"
          strokeWidth="1.5"
        />
      ))}
      <text x={460} y={130} textAnchor="middle" fontSize="8" fill="var(--muted-foreground)">
        relationships
      </text>
    </svg>
  )
}

/**
 * ENHANCE diagram — the Accept/Reject diff flow: an "original" box, a sparkle arrow,
 * and a "suggestion" box with one removed word (struck) and one added word. This is
 * the visual for the app's never-silently-overwrite seam (`enhance-diff.tsx`), so the
 * two colors deliberately mirror that real component's own `emerald-700`/`dark:emerald-300`
 * (added) and `red-700/80`/`dark:red-300/70` (removed) classes rather than introducing a
 * third, unrelated color scheme just for this diagram. Everything else stays on the
 * shared theme vars.
 */
function EnhanceDiffDiagram() {
  return (
    <div className="flex flex-col gap-2">
      <svg
        viewBox="0 0 460 90"
        className="h-auto w-full max-w-md"
        role="img"
        aria-label="Diagram: an original line becomes a suggestion with one word struck out and one word added"
        style={{ fontFamily: 'inherit' }}
      >
        <title>Enhance shows a suggestion beside your original line</title>
        <defs>
          <marker
            id="help-enhance-arrow"
            viewBox="0 0 8 8"
            refX="6"
            refY="4"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M0,0 L8,4 L0,8 Z" fill="var(--muted-foreground)" />
          </marker>
        </defs>

        <rect x={10} y={15} width={140} height={50} rx={10} fill="var(--card)" stroke="var(--border)" />
        <text x={20} y={34} fontSize="9" fill="var(--muted-foreground)">
          Original
        </text>
        <text x={20} y={52} fontSize="10" fill="var(--foreground)">
          The kign was brave.
        </text>

        <line
          x1={155}
          y1={40}
          x2={200}
          y2={40}
          stroke="var(--muted-foreground)"
          strokeWidth="1.5"
          markerEnd="url(#help-enhance-arrow)"
        />
        <path
          d="M177,25 l2.2,5.5 l5.5,2.2 l-5.5,2.2 l-2.2,5.5 l-2.2,-5.5 l-5.5,-2.2 l5.5,-2.2 z"
          fill="var(--primary)"
        />

        <rect x={205} y={15} width={245} height={50} rx={10} fill="var(--card)" stroke="var(--border)" />
        <text x={215} y={34} fontSize="9" fill="var(--muted-foreground)">
          Suggestion
        </text>
        <text x={215} y={52} fontSize="10" fill="var(--foreground)">
          The{' '}
          <tspan className="fill-red-700/80 dark:fill-red-300/70" textDecoration="line-through">
            kign
          </tspan>{' '}
          <tspan className="fill-emerald-700 dark:fill-emerald-300" fontWeight={600}>
            king
          </tspan>{' '}
          was brave.
        </text>
      </svg>

      <div className="flex items-center gap-2">
        <Badge variant="outline" className="gap-1 border-primary/40 text-primary">
          <Check className="size-3" />
          Accept
        </Badge>
        <Badge variant="outline" className="gap-1 border-destructive/40 text-destructive">
          <X className="size-3" />
          Reject
        </Badge>
      </div>
    </div>
  )
}

/** PROFILES diagram — two profile avatars, both wired to one shared Library, so
 * "everyone shares the Library, no one shares Reading Comfort settings" reads at a
 * glance. Kept small — text still carries most of this section. */
function ProfilesDiagram() {
  return (
    <svg
      viewBox="0 0 320 120"
      className="h-auto w-full max-w-xs"
      role="img"
      aria-label="Diagram: two profile avatars, both connected to one shared Library"
      style={{ fontFamily: 'inherit' }}
    >
      <title>Two profiles, one shared Library</title>
      <circle cx={70} cy={30} r={22} fill="var(--primary)" fillOpacity={0.15} stroke="var(--primary)" strokeWidth="1.5" />
      <text x={70} y={35} textAnchor="middle" fontSize="12" fontWeight={600} fill="var(--primary)">
        A
      </text>
      <circle cx={250} cy={30} r={22} fill="var(--primary)" fillOpacity={0.15} stroke="var(--primary)" strokeWidth="1.5" />
      <text x={250} y={35} textAnchor="middle" fontSize="12" fontWeight={600} fill="var(--primary)">
        B
      </text>
      <line x1={70} y1={52} x2={140} y2={90} stroke="var(--muted-foreground)" strokeWidth="1.3" />
      <line x1={250} y1={52} x2={180} y2={90} stroke="var(--muted-foreground)" strokeWidth="1.3" />
      <rect x={110} y={90} width={100} height={24} rx={12} fill="var(--card)" stroke="var(--border)" />
      <text x={160} y={106} textAnchor="middle" fontSize="9" fill="var(--foreground)">
        Shared Library
      </text>
    </svg>
  )
}

/** Getting Started — the numbered path from a blank Library to a shaped draft. */
function GettingStartedSection() {
  return (
    <div className="flex flex-col gap-4 py-2">
      <P>
        Quillnight is a dyslexia-friendly writing app. Here's the short path from a blank
        Library to a shaped story.
      </P>

      <GettingStartedFlow />

      <ol className="flex flex-col gap-3 text-sm">
        {[
          {
            title: 'Create a book',
            body: 'In the Library, add a new Book — a story book, a script, or a single scene.',
          },
          {
            title: 'Open it to the Canvas',
            body: 'Every Book opens on its Canvas tab — a big open space for laying out ideas.',
          },
          {
            title: 'Add a node',
            body: 'Use "Add node" in the toolbar to drop a Scene, Plot Point, or Thought onto the canvas.',
          },
          {
            title: 'Write in a node',
            body: 'Click a node to open its editor. Type your scene — watch the word count ("N penned") in the top-right of the canvas tick up as you write.',
          },
          {
            title: 'Try Enhance',
            body: (
              <>
                Click "Enhance" on a scene or element for an AI grammar-and-clarity pass. You
                review every suggestion before anything is saved —{' '}
                <ScrollHighlight badge="Trust">nothing is ever overwritten silently</ScrollHighlight>.
              </>
            ),
          },
          {
            title: 'Build your Codex',
            body: 'Add characters, locations, factions, and objects in the Codex, then link them to scenes so their details travel with your story.',
          },
          {
            title: 'Shape and compile',
            body: 'Switch to the Outline and Draft tabs (next to Canvas) to arrange scenes in order and compile your manuscript.',
          },
        ].map((step, index) => (
          <li key={step.title} className="flex gap-3">
            <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
              {index + 1}
            </span>
            <div>
              <p className="font-medium">{step.title}</p>
              <p className="text-muted-foreground">{step.body}</p>
            </div>
          </li>
        ))}
      </ol>

      <Example>
        <p>
          Start a "Story Book" called <strong>Ashwood</strong>. Add one Scene node titled{' '}
          <em>Arrival</em>. Write two sentences in it. Then add a Character in the Codex named{' '}
          <em>Kael</em> and link him to that scene.
        </p>
      </Example>

      <div className="rounded-xl border border-border bg-muted/40 p-3 text-sm text-muted-foreground">
        <strong className="text-foreground">A note on Enhance:</strong> AI features run
        offline on a local model, online through your own Groq key, or a hybrid of both —
        pick a mode in <strong>Settings → AI</strong>. Enhance is available on this screen
        either way, but it needs one of those set up first.{' '}
        <ScrollHighlight>Nothing you write is ever sent anywhere</ScrollHighlight> without you
        choosing an online/hybrid mode.
      </div>
    </div>
  )
}

/** The Canvas — nodes, connections, and the minimap/zoom chrome around them. */
function CanvasSection() {
  return (
    <div className="flex flex-col gap-4 py-2">
      <CanvasDiagram />

      <H3>Nodes</H3>
      <P>Three kinds of node, all added from the "Add node" button in the toolbar:</P>
      <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
        <li>
          <strong className="text-foreground">Scene</strong> — a real beat of your story, with
          a description (or, in a script, structured screenplay elements).
        </li>
        <li>
          <strong className="text-foreground">Plot Point</strong> — a marker for something that
          needs to happen, without full prose yet.
        </li>
        <li>
          <strong className="text-foreground">Thought</strong> — a loose idea you don't want to
          lose, not yet attached to a scene.
        </li>
      </ul>

      <Separator />

      <H3>Connecting and arranging</H3>
      <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
        <li>Drag from one node's handle to another to draw a connection between them.</li>
        <li>Drag a node anywhere on the canvas — its position is saved automatically.</li>
        <li>
          Select a node and press Delete/Backspace to remove it, or open it and use "Remove
          from canvas" (keeps it in the Library) versus "Delete scene permanently" (gone
          everywhere — the app always asks first).
        </li>
      </ul>

      <Separator />

      <H3>Minimap, zoom, and word count</H3>
      <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
        <li>
          <span className="inline-flex items-center gap-1 font-medium text-foreground">
            <Map className="size-3.5" /> Minimap
          </span>{' '}
          — bottom-right corner of the canvas. A small overview of every node; drag or click
          inside it to jump around a large canvas, and it's pannable and zoomable on its own.
        </li>
        <li>
          <span className="font-medium text-foreground">Zoom controls</span> — top-right,
          just under the word-count pill. Zoom in/out or fit everything into view.
        </li>
        <li>
          <span className="font-medium text-foreground">Word count</span> — the "N penned"
          pill, top-right, is the total across every node on this canvas.
        </li>
      </ul>

      <Example>
        <p>
          Lost among 30 nodes? Glance at the minimap in the bottom-right corner, click the
          area you want, and the main canvas jumps there. Use the fit-view zoom control to
          see everything at once again.
        </p>
      </Example>
    </div>
  )
}

/** Codex — the four entity types and the entry editor's five tabs. */
function CodexSection() {
  return (
    <div className="flex flex-col gap-4 py-2">
      <CodexDiagram />

      <P>The Codex holds everything about your story world, in four entity types:</P>
      <div className="flex flex-wrap gap-1.5">
        {['Character', 'Location', 'Faction', 'Object / Lore'].map((label) => (
          <Badge key={label} variant="outline">
            {label}
          </Badge>
        ))}
      </div>

      <Separator />

      <H3>The entry editor</H3>
      <P>Open the edit control on any Codex row to get a five-tab editor:</P>
      <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
        <li>
          <strong className="text-foreground">Details</strong> — name, summary, role/kind,
          and traits.
        </li>
        <li>
          <strong className="text-foreground">Custom Fields</strong> — free-form name/value
          pairs you want to track.
        </li>
        <li>
          <strong className="text-foreground">Relationships</strong> — cross-link this entry
          to any other Codex entry, with a type and description.
        </li>
        <li>
          <strong className="text-foreground">Image</strong> — one reference image.
        </li>
        <li>
          <strong className="text-foreground">Arc States</strong> — a point-in-time status
          for this entry. <ScrollHighlight badge="Spoiler-safe" hue={155}>Anti-spoiler by design</ScrollHighlight>:
          only arc states at or before a scene's own outline position are ever used to inform
          that scene.
        </li>
      </ul>

      <Example>
        <p>
          Link <strong>Kael</strong> to <strong>Dain</strong> with relationship type{' '}
          <em>rival</em>. Then, on Kael's Arc States tab, add one at outline index 3 with the
          summary <em>"Injured in the ambush."</em> — scenes before that point never see it.
        </p>
      </Example>
    </div>
  )
}

/** Reading comfort — per-profile Settings that tune the manuscript surface. */
function ReadingComfortSection() {
  return (
    <div className="flex flex-col gap-4 py-2">
      <P>
        In <strong>Settings</strong>, tune how your own writing looks and feels on the page.
        These are yours — they don't change what anyone else on this computer sees.
      </P>
      <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
        <li>
          <strong className="text-foreground">Font</strong> — Lexend by default (built for
          reading comfort), plus other dyslexia-friendly options.
        </li>
        <li>
          <strong className="text-foreground">Font size, letter spacing, line height, line
          length</strong> — four sliders, each with a marked evidence-backed default.
        </li>
        <li>
          <strong className="text-foreground">Theme</strong> — Day, Night, or Auto (by local
          time).
        </li>
        <li>
          <strong className="text-foreground">Delight level</strong> — Calm, Standard, or
          Playful: controls motion, sound, and celebratory touches app-wide.
        </li>
      </ul>
      <P>
        You can re-run the first-time Reading Comfort wizard any time from the "Re-run
        wizard" button at the top of the Reading Comfort section.
      </P>

      <Separator />

      <H3>Keyboard shortcuts (Draft tab)</H3>
      <P>
        While reading the manuscript view on the Draft tab, two single-key shortcuts help you
        keep your place — they only work there, and never while you're typing:
      </P>
      <ul className="flex flex-col gap-2 text-sm text-muted-foreground">
        <li className="flex items-start gap-2">
          <Kbd>R</Kbd>
          <span>
            <strong className="text-foreground">Reading ruler</strong> — cycles through off, a
            grey bar, and a soft shade under your current line to help you track it as you read.
          </span>
        </li>
        <li className="flex items-start gap-2">
          <Kbd>F</Kbd>
          <span>
            <strong className="text-foreground">Focus mode</strong> — dims everything except
            the paragraph you're currently reading.
          </span>
        </li>
      </ul>
    </div>
  )
}

/** Profiles — the 2-profile local picker and what's shared vs. personal. */
function ProfilesSection() {
  return (
    <div className="flex flex-col gap-4 py-2">
      <P>Quillnight supports up to two local profiles on one computer.</P>

      <ProfilesDiagram />

      <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
        <li>Each profile has its own password, avatar, and Reading Comfort/theme/delight settings.</li>
        <li>The Library — every Book and the shared Codex — is common to both profiles.</li>
        <li>
          Switch profiles from the sidebar: click your name/avatar at the bottom to sign out
          and return to the profile picker.
        </li>
      </ul>
      <Example>
        <p>
          One writer prefers Night theme with a larger font; the other prefers Day theme at
          the default size. Both open the same book and see the same scenes — just rendered
          to their own comfort settings.
        </p>
      </Example>
    </div>
  )
}

/** One shortcut row: a keycap, a bold name, and a plain-language description. */
function ShortcutRow({
  keys,
  name,
  children,
}: {
  keys: string
  name: string
  children: ReactNode
}) {
  return (
    <li className="flex items-start gap-2">
      <Kbd>{keys}</Kbd>
      <span>
        <strong className="text-foreground">{name}</strong> — {children}
      </span>
    </li>
  )
}

/** Keyboard shortcuts — every hotkey currently wired up in the app, grouped by where it
 * works. Kept in one place (rather than only mentioned in-context, as Reading Comfort's `R`/`F`
 * still also are above) so a keyboard-first writer can find the full list without hunting
 * through every other tab. Scope is called out explicitly wherever a shortcut isn't global. */
function KeyboardShortcutsSection() {
  return (
    <div className="flex flex-col gap-4 py-2">
      <P>
        Quillnight can be driven almost entirely from the keyboard. Here's every shortcut that
        exists today, grouped by where it works.
      </P>

      <H3>Search (anywhere in the app)</H3>
      <ul className="flex flex-col gap-2 text-sm text-muted-foreground">
        <ShortcutRow keys="Ctrl/Cmd+K" name="Open search">
          opens the library-wide search dialog from any screen.
        </ShortcutRow>
      </ul>

      <Separator />

      <H3>Canvas (while a Book's Canvas tab is open)</H3>
      <ul className="flex flex-col gap-2 text-sm text-muted-foreground">
        <ShortcutRow keys="Shift+N" name="Add node">
          adds a new Scene node to the canvas and moves keyboard focus straight to it.
        </ShortcutRow>
        <ShortcutRow keys="Shift+C" name="Connect nodes">
          with a node focused, starts a connection from it; Tab to another node and press
          Shift+C (or Enter) again to confirm the connection between them.
        </ShortcutRow>
        <ShortcutRow keys="Enter" name="Open node">
          with a node focused, opens its editor. Also confirms an in-progress connection (see
          Shift+C above) if one is active.
        </ShortcutRow>
        <ShortcutRow keys="Escape" name="Cancel connection">
          cancels an in-progress Shift+C connection without creating it.
        </ShortcutRow>
      </ul>

      <Separator />

      <H3>Reading (only on the Draft tab's manuscript view)</H3>
      <P>
        These two only work while you're reading the compiled manuscript on the Draft tab, and
        never while you're typing anywhere:
      </P>
      <ul className="flex flex-col gap-2 text-sm text-muted-foreground">
        <ShortcutRow keys="R" name="Reading ruler">
          cycles through off, a grey bar, and a soft shade under your current line.
        </ShortcutRow>
        <ShortcutRow keys="F" name="Focus mode">
          dims everything except the paragraph you're currently reading.
        </ShortcutRow>
      </ul>
    </div>
  )
}

/** Tips — a couple of end-to-end mini-workflows tying the sections together. */
function TipsSection() {
  return (
    <div className="flex flex-col gap-4 py-2">
      <H3>Tip 1 — draft first, connect later</H3>
      <P>
        Don't worry about wiring nodes together right away. Drop a handful of Thought and
        Plot Point nodes as they occur to you, then come back and connect them once the
        shape of the story is clearer.
      </P>

      <Example>
        <p>
          Add three Thought nodes: <em>"opens on rooftop"</em>,{' '}
          <em>"reveal Kael's past"</em>, <em>"final confrontation"</em>. Later, connect them in
          order and upgrade each to a full Scene as you write it.
        </p>
      </Example>

      <Separator />

      <H3>Tip 2 — let Enhance do the polishing, not the writing</H3>
      <P>
        Write your first pass in your own voice. Then use Enhance for a grammar-and-clarity
        pass — it only ever shows a suggestion side-by-side with your original. You choose
        Accept or Reject; nothing is saved until you accept it.
      </P>

      <EnhanceDiffDiagram />
    </div>
  )
}

interface Topic {
  id: string
  label: string
  icon: typeof BookOpen
  content: ReactNode
}

const TOPICS: Topic[] = [
  { id: 'start', label: 'Getting Started', icon: Compass, content: <GettingStartedSection /> },
  { id: 'canvas', label: 'Canvas', icon: Map, content: <CanvasSection /> },
  { id: 'codex', label: 'Codex', icon: BookOpen, content: <CodexSection /> },
  { id: 'reading', label: 'Reading Comfort', icon: ScrollText, content: <ReadingComfortSection /> },
  { id: 'profiles', label: 'Profiles', icon: Users, content: <ProfilesSection /> },
  {
    id: 'shortcuts',
    label: 'Keyboard Shortcuts',
    icon: Keyboard,
    content: <KeyboardShortcutsSection />,
  },
  { id: 'tips', label: 'Tips', icon: Lightbulb, content: <TipsSection /> },
]

/** The left topic rail — a real vertical list of `<button>`s (not a `Tabs`/`TabsList`, so
 * there's no horizontal overflow strip to fight on a small width). The active state itself
 * (`aria-current`, the `bg-accent`/`font-medium` styling) always applies instantly; only the
 * `transition-colors` decoration on top of it is gated on `useDelight().motionOk`, matching
 * `characters-panel.tsx`'s `AlphabetIndexRail` convention — the affordance is never gated,
 * only the animation. */
function HelpRail({
  activeId,
  onSelect,
}: {
  activeId: string
  onSelect: (id: string) => void
}) {
  const { motionOk } = useDelight()

  return (
    <nav
      aria-label="Help topics"
      className="flex w-44 shrink-0 flex-col gap-0.5 overflow-y-auto border-r border-border p-2"
    >
      {TOPICS.map(({ id, label, icon: Icon }) => {
        const isActive = id === activeId
        return (
          <button
            key={id}
            type="button"
            onClick={() => onSelect(id)}
            aria-current={isActive ? 'true' : undefined}
            className={cn(
              'flex items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm',
              'focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
              isActive
                ? 'bg-accent font-medium text-accent-foreground'
                : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground',
              motionOk && 'transition-colors',
            )}
          >
            <Icon className="size-4 shrink-0" />
            <span className="truncate">{label}</span>
          </button>
        )
      })}
    </nav>
  )
}

/**
 * In-app Help & Guide: a discoverable "?" entry that opens a scrollable walkthrough of the
 * whole app (getting started, Canvas, Codex, Reading Comfort, Profiles, shortcuts, tips).
 * Static, self-contained content — no backend, no query.
 *
 * Two-pane layout: a left topic rail (`HelpRail`) and a right `ScrollArea` content pane,
 * replacing the old horizontal, overflow-scrolling `TabsList` — every topic now also gets a
 * small themed SVG diagram beside its (shortened where possible) text.
 *
 * `triggerClassName`/`triggerLabel` let callers (the sidebar nav) match this trigger's
 * styling exactly to the Library/Settings nav items without duplicating markup here.
 */
export function HelpGuide({
  triggerClassName,
  triggerLabel = 'Help',
}: {
  triggerClassName?: string
  triggerLabel?: string
}) {
  const [activeId, setActiveId] = useState<string>(TOPICS[0].id)
  const active = TOPICS.find((topic) => topic.id === activeId) ?? TOPICS[0]

  return (
    <Dialog>
      <DialogTrigger asChild>
        <button type="button" className={cn(triggerClassName)} aria-label="Open the Help & Guide">
          <HelpCircle className="size-4" />
          {triggerLabel}
        </button>
      </DialogTrigger>
      <DialogContent className="flex max-h-[85vh] flex-col gap-0 overflow-hidden sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <HelpCircle className="size-5 text-primary" />
            Help & Guide
          </DialogTitle>
          <DialogDescription>
            A friendly walkthrough of how Quillnight works — short steps, plain language.
          </DialogDescription>
        </DialogHeader>

        {/* A DEFINITE height on this row (not `flex-1` off the centered dialog's indefinite
            `max-h`) is what lets the ScrollArea below actually scroll instead of growing to its
            content height and bleeding past the dialog — same definite-height approach the
            other centered dialogs in the app use (e.g. the attach-character picker). */}
        <div className="flex h-[62vh] min-h-0">
          <HelpRail activeId={activeId} onSelect={setActiveId} />
          <ScrollArea className="h-full flex-1">
            <div className="flex flex-col gap-4 p-4">{active.content}</div>
          </ScrollArea>
        </div>
      </DialogContent>
    </Dialog>
  )
}
