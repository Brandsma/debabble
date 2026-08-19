# debabble

Install no-AI-speak writing rules into your AI coding tools, per project or
user-wide.

AI assistants write in a recognisable way: "delve", "seamless", "it is important
to note", "not just X, but Y", emoji-headed READMEs, comments that restate the
line below them, commit messages that narrate instead of stating. debabble keeps
a curated set of rules against those habits and writes them into the instruction
files your tools already read, so the rules shape what gets generated rather
than being cleaned up afterwards.

## Install

```bash
uv tool install debabble
```

Or run it without installing:

```bash
uvx debabble status
```

## Use

```bash
debabble apply
```

That writes the default packs into `.claude/rules/debabble.md` in the current
project. To set up your tools once for every project:

```bash
debabble apply --global
```

To see what is installed and whether it is current:

```bash
debabble status
```

To take it back out:

```bash
debabble remove
```

Every command that writes accepts `--dry-run`, which shows the changes and
writes nothing.

## Choosing tools

```bash
debabble targets
```

lists every supported tool and the exact file it writes for the current scope.
Pick the ones you use:

```bash
debabble apply --target claude-code --target cursor --target agents-md
```

| Target | Project file | User-wide file |
| --- | --- | --- |
| `claude-code` | `.claude/rules/debabble.md` | `~/.claude/rules/debabble.md` |
| `claude-command` | `.claude/commands/debabble.md` | `~/.claude/commands/debabble.md` |
| `cursor` | `.cursor/rules/debabble.mdc` | kept in Cursor's settings; use `render` |
| `agents-md` | `AGENTS.md` | `~/.codex/AGENTS.md` |
| `copilot` | `.github/instructions/debabble.instructions.md` | covered by `claude-code` |
| `windsurf` | `.windsurf/rules/debabble.md` | `~/.codeium/windsurf/memories/global_rules.md` |
| `gemini` | `GEMINI.md` | `~/.gemini/GEMINI.md` |
| `hermes` | `.hermes.md` | `SOUL.md` in your Hermes home |
| `cline` | `.clinerules/debabble.md` | `~/Documents/Cline/Rules/debabble.md` |
| `roo` | `.roo/rules/debabble.md` | `~/.roo/rules/debabble.md` |
| `amazon-q` | `.amazonq/rules/debabble.md` | not available |
| `kiro` | `.kiro/steering/debabble.md` | `~/.kiro/steering/debabble.md` |

Where a tool reads a directory of rule files, debabble owns one file in it and
nothing you wrote is at risk. Where a tool reads a single file you also write in
(`AGENTS.md`, `GEMINI.md`, `.hermes.md`), debabble keeps its content between
markers and replaces only what is between them.

`claude-command` is different from the rest: instead of rules that shape new
writing, it installs a `/debabble` command that rewrites text you already have.

## The rules

```bash
debabble packs          # the packs, and which are on
debabble rules          # every rule in effect
debabble rules vocabulary.hype-verbs     # one rule in full
```

Rules come at two severities. A **ban** is absolute: never do this. A **flag** is
density guidance: fine once, a tell in clusters. The split matters, because
banning ordinary words teaches a model to write around the ban instead of
writing plainly.

An instruction file is read on every request, so its size is a real cost.
`debabble apply` prints how much it is asking for, and three styles trade
completeness against context: `minimal` carries the bans only, `compact` states
every active rule, and `full` adds a wrong/right example to each. Narrowing
`packs` is the other lever.

Packs on by default: `chat-artifacts`, `vocabulary`, `phrases`, `structure`,
`punctuation`, `code-comments`, `commits`, `docs-readme`, `minimal-docs`.
`corporate-speak` is available but off unless you ask for it.

## Making it yours

The shipped rules are a starting point. Three ways to change them, shortest
first.

**Ban a word.**

```bash
debabble avoid supercharge
```

**Change how hard a rule pushes**, or switch it off. This works on a single rule
or a whole pack:

```bash
debabble severity vocabulary.intensity-cluster off
debabble severity corporate-speak ban
```

**Edit a rule outright.** `debabble rules <id>` prints the rule as TOML in
exactly the format the config accepts, so you can paste it into `debabble.toml`
and change anything: the wording, the word list, the examples, the severity.

```toml
[[rules]]
id = "vocabulary.hype-verbs"
severity = "flag"
words = ["delve", "leverage", "showcase"]
instruction = "Say what the action actually is."
```

The same block with an id nobody has used defines a brand new rule. Drop a whole
pack file in `.debabble/packs/` to share a set of rules through a repository.

Anything you can do in the file you can also do for one run:

```bash
debabble apply --pack vocabulary --pack phrases --severity phrases=flag --avoid synergize
```

## Configuration

`debabble init` writes a starter `debabble.toml` with every section commented.

```toml
[profile]
packs = ["chat-artifacts", "vocabulary", "phrases"]
targets = ["claude-code", "cursor"]
style = "compact"     # or "minimal" for the bans only, "full" to add examples

[severity]
"vocabulary.intensity-cluster" = "off"

[custom]
avoid = ["supercharge"]
allow = ["robust"]    # keep using a word a shipped rule bans
```

A project with its own `debabble.toml` is self-contained: your personal global
config is ignored, so everyone who clones the repository generates identical
files. A project without one falls back to your global config, which is what
makes `debabble apply --global` useful as a personal default.

Config lives in `debabble.toml` at the project root, and globally at:

- Windows: `%LOCALAPPDATA%\debabble\debabble.toml`
- macOS: `~/Library/Application Support/debabble/debabble.toml`
- Linux: `~/.config/debabble/debabble.toml`

## What gets committed

`.debabble/manifest.toml` records what was installed where. Commit it: that is
what lets `debabble status` and `debabble remove` work for anyone who clones the
repository. Backups are machine-local, kept in `.debabble/backups/`, and
gitignored automatically.

## Where the rules come from

The rules are written from published research rather than from taste alone.
`research/` holds the source material, including Wikipedia's "Signs of AI
writing", the Kobak et al. study of excess vocabulary in scientific abstracts,
and the Antislop paper's measurements of how much more often some phrases appear
in model output than in human writing. Each pack cites its references.

Vocabulary tells drift between model generations, so vocabulary rules carry an
`era` tag and the packs are versioned separately from the tool.

The project was inspired by [Declaude](https://github.com/danielrosehill/Declaude),
which had the good idea of keeping writing grievances as small editable rule
files. Nothing is copied from it; the rules here are written fresh.

## Development

```bash
uv sync
uv run pytest
uv run ruff check
```

## Licence

MIT.
