# claude-fork-rename

English · [中文](README.zh-CN.md)

Give every forked Claude Code session a name of its own.

Fork a session and the new one inherits its parent's name with a `(fork)` /
`(fork 2)` suffix. A few forks in, the sidebar is a wall of identical rows:

```
Today
  Checkout refactor (fork)
  Checkout refactor (fork)
  Checkout refactor (fork 2)
  Checkout refactor (fork)
  Checkout refactor (fork)
```

With this installed, each fork renames itself on its **first prompt with actual
content**:

```
Today
  frontend · empty cart state
  frontend · form validation copy
  api · refund callback timeouts
  deploy · canary flag not read
  ci · cache hit rate
```

## Install

Pick one.

**As a plugin** — one line in a session, on Claude Code 2.1.275 or later:

```
/plugin install fork-rename --marketplace ShadowNearby/claude-fork-rename
```

On earlier versions, two steps:

```
/plugin marketplace add ShadowNearby/claude-fork-rename
/plugin install fork-rename@claude-fork-rename
```

**As a one-liner** in your shell:

```bash
curl -fsSL https://raw.githubusercontent.com/ShadowNearby/claude-fork-rename/main/install.sh | bash
```

**From a checkout**, which also gets you `fork-topics.py`:

```bash
git clone https://github.com/ShadowNearby/claude-fork-rename
cd claude-fork-rename && ./install.sh
```

The plugin keeps the hook inside itself and registers it from there, so your
`settings.json` gains nothing but the plugin being enabled. The script routes
install into your Claude config directory (`$CLAUDE_CONFIG_DIR`, `~/.claude` by
default) instead:

| File | What it is |
| --- | --- |
| `hooks/fork-rename.py` | the hook itself, standard library only |
| `settings.json` | one merged `UserPromptSubmit` entry (backed up first) |
| `fork-rename.json` | your config, left alone if it already exists |

Either way it takes effect in **sessions started afterwards**, and both read the
same `~/.claude/fork-rename.json`. To remove it: `/plugin uninstall fork-rename`,
or `./install.sh --uninstall`, which only takes out its own entry.

## How it works

The hook runs on every prompt and exits silently unless the session's name
still looks inherited. From there the two surfaces work differently, because
only one of them has a rename tool:

**Desktop app (Code tab).** The hook injects a short instruction into the
model's context, and the model calls the app's own
`mcp__ccd_session_mgmt__set_session_title` on itself. Nothing is renamed behind
the model's back, permissions follow the app's usual rules, and because the
hook reads the session's real name from the app's records, a name *you* edited
is never touched.

**Terminal.** There is no such tool (renaming there is your own `/rename`), so
the hook writes the title itself through its output's `sessionTitle` field,
built from the prompt's own words — code fences, URLs, long paths and openers
like "please" or "can you" stripped, cut at the first sentence break, 7 words
or 24 CJK characters.

```
$ claude
> the cart renders blank when it's empty, add an empty state
  → titled "cart renders blank when it's empty"
```

Each session is reminded at most once; the marker lives in
`~/.claude/fork-rename/<session id>`. If a rename is refused, the hook does not
nag on every later prompt.

## Configuration

`~/.claude/fork-rename.json`, every key optional. To see what is in effect:

```bash
python3 ~/.claude/hooks/fork-rename.py --print-config
```

```jsonc
{
  // Shape of the title. Pick one:
  //   "domain"  →  "frontend · empty cart state"   area first; areas sort together
  //   "topic"   →  "empty cart state"              shortest; no lineage
  //   "parent"  →  "Checkout refactor · empty cart state"
  "style": "domain",

  // Terminal (non-desktop) sessions:
  //   "untitled" title a session with no title visible yet (default)
  //   "always"   retitle even one that has a title (a --resume you took elsewhere)
  //   "off"      leave terminal sessions alone
  "terminal": "untitled",

  // Example areas handed to the model under "domain". Use the modules you
  // actually work on; leave empty and the model judges from the project.
  "domains": ["frontend", "api", "database", "deploy", "ci", "docs"],

  // Language of the instruction and the title: "zh", "en", "auto" (follow the prompt)
  "language": "auto",

  // Prompts shorter than this are skipped (an image-only paste lands here)
  "min_prompt_chars": 4,

  // Prompts starting with any of these are skipped
  "skip_prefixes": ["/", "!"],

  // Added to the built-in filler list ("ok", "continue", "go on", ...)
  "extra_filler": [],

  // Remind once per session. false = keep reminding while the name looks inherited
  "remind_once": true
}
```

### Why the default puts the area first

Three iterations got here:

1. **`parent · topic`** — every row starts with the same parent name, so what
   tells them apart is pushed to the right edge, past where you stop reading.
2. **Topic alone** — short, but everything from one project piles up: three
   rows starting "display page…" still have to be opened to be told apart.
3. **`area · topic`** — the most useful word comes first, and sorting the
   sidebar by name groups a module's sessions into one run.

Marking fork depth with `#` / `##` was considered and dropped: nearly every fork
is one level deep, so the mark lands on all of them and separates nothing.
Lineage is already recorded by the app as `startedBy`.

Change `style`, or edit `title_spec()` in the hook if you want a different shape.

## The forks already in your sidebar

The hook only renames from the next prompt on. For the ones already there, see
what each of them actually did:

```bash
python3 fork-topics.py               # forks whose name is still inherited
python3 fork-topics.py --days 14     # only transcripts touched in the last 14 days
python3 fork-topics.py --scope forks # anything that opened on copied history
python3 fork-topics.py <uuid> ...    # just these
```

```
========================================================================
3c7f91a2  Checkout refactor (fork)
   ~/.claude/projects/-Users-me-code-thing/3c7f91a2-….jsonl
   user 1: the cart renders blank when it's empty, add an empty state
   asst 1: The empty-cart branch renders nothing; adding the empty state…
========================================================================
1 shown
```

Rename them by hand from that, or hand the output to Claude and let it call
`set_session_title` for each.

It prints assistant lines as well as prompts on purpose: a fork's first prompt
is often just a pasted screenshot with no text, and then the topic is only
visible in the reply.

A fork's transcript opens with its parent's history copied in, and in the
desktop app **those copied lines keep the parent's `sessionId`** — so a fork's
own work is exactly the lines whose `sessionId` matches the file name. That is
the whole trick behind `fork-topics.py`. The converse does not hold: a
transcript merely starting with copied history also describes a resume or a
compaction, which is why the default scope goes by the name instead. The CLI's
`--fork-session` rewrites the copied lines to the new session's id, so this
trick is desktop-only.

## What it does not do

- **Cannot tell inherited from hand-picked in a terminal.** The desktop path
  reads the session's real name and skips anything you renamed yourself. The
  terminal path cannot: a fork's transcript — inherited title included — is
  still unwritten when the hook runs, which is also *why* terminal forks get
  named at all. Fork a session you named carefully and the terminal will title
  the fork after its new prompt.
- **Leaves resumed sessions alone** by default. Their transcript and title are
  already on disk, so `untitled` skips them. Set `terminal: "always"` if you
  resume sessions and change the subject.
- **`sessionTitle` on `UserPromptSubmit` is undocumented.** It is documented for
  `SessionStart` only; it works here and has been verified, but it is not a
  contract. If it stops working the terminal path degrades to doing nothing and
  the desktop path is unaffected.
- **New sessions only.** A session already running when you change settings may
  not pick the hook up.
- **Nothing in the cloud.** Cloud and SSH sessions do not read your local
  `~/.claude`; they follow whatever is configured where they run.
- **Never names a fork that was never prompted.** No prompt, no topic — those
  keep the inherited name.

The script runs on every prompt in every session, around 60 ms, and every
failure path is a silent no-op: a broken config, an unreadable transcript or a
malformed hook payload all exit 0 without touching your prompt.

## License

MIT
