import type { ReactNode } from 'react'
import {
  BookOpen,
  Compass,
  HelpCircle,
  Lightbulb,
  Map,
  ScrollText,
  Sparkles,
  Users,
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

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

/** Getting Started — the numbered path from a blank Library to a shaped draft. */
function GettingStartedSection() {
  return (
    <div className="flex flex-col gap-4 py-2">
      <P>
        Quillnight is a dyslexia-friendly writing app. Here's the short path from a blank
        Library to a shaped story.
      </P>
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
            body: 'Click "Enhance" on a scene or element for an AI grammar-and-clarity pass. You review every suggestion before anything is saved — nothing is ever overwritten silently.',
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
        either way, but it needs one of those set up first. Nothing you write is ever sent
        anywhere without you choosing an online/hybrid mode.
      </div>
    </div>
  )
}

/** The Canvas — nodes, connections, and the minimap/zoom chrome around them. */
function CanvasSection() {
  return (
    <div className="flex flex-col gap-4 py-2">
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
          <strong className="text-foreground">Details</strong> — name, summary, a role/kind
          (e.g. Protagonist, City, Guild), and character traits.
        </li>
        <li>
          <strong className="text-foreground">Custom Fields</strong> — any free-form
          name/value pairs you want to track.
        </li>
        <li>
          <strong className="text-foreground">Relationships</strong> — cross-link this entry
          to any other Codex entry, with a relationship type and description.
        </li>
        <li>
          <strong className="text-foreground">Image</strong> — attach one reference image.
        </li>
        <li>
          <strong className="text-foreground">Arc States</strong> — a point-in-time status
          for this entry, tied to a book and an outline position. Anti-spoiler by design:
          only arc states at or before a scene's own outline position are ever used to
          inform that scene.
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
      <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
        <li>
          <Badge variant="outline" className="mr-1.5 font-mono">R</Badge>
          <strong className="text-foreground">Reading ruler</strong> — cycles through off, a
          grey bar, and a soft shade under your current line to help you track it as you read.
        </li>
        <li>
          <Badge variant="outline" className="mr-1.5 font-mono">F</Badge>
          <strong className="text-foreground">Focus mode</strong> — dims everything except the
          paragraph you're currently reading.
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

      <H3>Tip 2 — let Enhance do the polishing, not the writing</H3>
      <P>
        Write your first pass in your own voice. Then use Enhance for a grammar-and-clarity
        pass — it only ever shows a suggestion side-by-side with your original. You choose
        Accept or Reject; nothing is saved until you accept it.
      </P>
    </div>
  )
}

interface Section {
  id: string
  label: string
  icon: typeof BookOpen
  content: ReactNode
}

const SECTIONS: Section[] = [
  { id: 'start', label: 'Getting Started', icon: Compass, content: <GettingStartedSection /> },
  { id: 'canvas', label: 'Canvas', icon: Map, content: <CanvasSection /> },
  { id: 'codex', label: 'Codex', icon: BookOpen, content: <CodexSection /> },
  { id: 'reading', label: 'Reading Comfort', icon: ScrollText, content: <ReadingComfortSection /> },
  { id: 'profiles', label: 'Profiles', icon: Users, content: <ProfilesSection /> },
  { id: 'tips', label: 'Tips', icon: Lightbulb, content: <TipsSection /> },
]

/**
 * In-app Help & Guide: a discoverable "?" entry that opens a scrollable walkthrough of the
 * whole app (getting started, Canvas, Codex, Reading Comfort, Profiles, tips). Static,
 * self-contained content — no backend, no query. Reuses the existing Dialog/Tabs/ScrollArea
 * primitives and the manuscript-adjacent reading tokens so the guide reads comfortably.
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
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button type="button" className={cn(triggerClassName)} aria-label="Open the Help & Guide">
          <HelpCircle className="size-4" />
          {triggerLabel}
        </button>
      </DialogTrigger>
      <DialogContent className="flex max-h-[85vh] flex-col gap-0 sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <HelpCircle className="size-5 text-primary" />
            Help & Guide
          </DialogTitle>
          <DialogDescription>
            A friendly walkthrough of how Quillnight works — short steps, plain language.
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="start" className="min-h-0 flex-1">
          <TabsList className="w-full flex-wrap justify-start gap-1 bg-transparent p-0">
            {SECTIONS.map(({ id, label, icon: Icon }) => (
              <TabsTrigger key={id} value={id} className="gap-1.5">
                <Icon className="size-3.5" />
                {label}
              </TabsTrigger>
            ))}
          </TabsList>

          {SECTIONS.map(({ id, content }) => (
            <TabsContent key={id} value={id} className="min-h-0 flex-1 data-[state=inactive]:hidden">
              <ScrollArea className="h-[52vh] pr-3">{content}</ScrollArea>
            </TabsContent>
          ))}
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}
