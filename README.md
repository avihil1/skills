# skills

Agent skills — self-contained instruction packs an AI coding agent loads on demand.

| Skill | What it does |
|---|---|
| [`israeli-tax-refund-filer`](israeli-tax-refund-filer/) | Prepares and files an Israeli tax return: parses Form 106 and donation receipts, computes the refund, generates a report and pre-filled PDF, and optionally drives the SHAAM portal. |

Each skill is a directory containing a `SKILL.md` plus any `scripts/` and `references/` it needs.
`SKILL.md` starts with YAML frontmatter:

```yaml
---
name: israeli-tax-refund-filer
description: Prepare and file an Israeli tax refund... Use when user says 'tax refund', 'החזר מס'...
allowed-tools: Bash(python3:*), Bash(pip:*), Bash(open:*), Read, Write, Edit
---
```

`name` and `description` are what an agent matches against to decide the skill applies, so the
description should name the trigger phrases. `allowed-tools` is honoured by Claude Code and
ignored by agents that have no equivalent — harmless either way.

## Adding a skill to an agent

### Claude Code

Skills are auto-discovered from two locations. Copy (or symlink) the skill directory into one:

```bash
# available in every project
git clone https://github.com/avihil1/skills /tmp/skills
cp -R /tmp/skills/israeli-tax-refund-filer ~/.claude/skills/

# or scoped to one project
mkdir -p .claude/skills && cp -R /tmp/skills/israeli-tax-refund-filer .claude/skills/
```

Symlinking instead of copying keeps it updatable with `git pull`:

```bash
ln -s /path/to/skills/israeli-tax-refund-filer ~/.claude/skills/israeli-tax-refund-filer
```

Then `/reload-skills`, or restart the session — the reload reports how many skills it found, which
is the quickest confirmation it registered. Invoke it directly as `/israeli-tax-refund-filer`.
Claude also triggers it on its own when a request matches the `description`.

### Codex

Codex has no skill auto-discovery — it reads markdown instruction files. Point it at the skill from
one of those files rather than duplicating the content:

```bash
# global, applies everywhere
cat >> ~/.codex/AGENTS.md <<'EOF'

## Israeli tax filing

When the user asks about an Israeli tax refund, החזר מס, Form 135, or דוח שנתי, read
`~/skills/israeli-tax-refund-filer/SKILL.md` and follow it exactly.
EOF
```

For a project, put the same pointer in the repo's `AGENTS.md`. If your repo uses a different
filename, list it under `project_doc_fallback_filenames` in `~/.codex/config.toml` so Codex picks
it up:

```toml
project_doc_fallback_filenames = ["AGENTS.md", "CLAUDE.md"]
```

A pointer beats pasting the skill inline: the instructions stay in one place, and Codex reads the
file only when the task actually calls for it instead of carrying it in every prompt.

### Any other agent

The pattern generalises to anything that reads a markdown instruction file — Cursor, Windsurf,
Gemini CLI, Copilot, Aider. Add a pointer to `SKILL.md` in whichever file that agent loads, keyed on
the same trigger phrases from the skill's `description`:

```
When the user mentions <trigger phrases>, read <path>/SKILL.md and follow it.
```

`SKILL.md` is plain markdown with no agent-specific syntax in its body, so it is portable as-is.
Only the frontmatter is Claude-Code-flavoured, and an agent that doesn't understand it will simply
read past it.

## Prerequisites

`israeli-tax-refund-filer` runs Python helpers:

```bash
pip install pdfplumber reportlab
playwright install chromium   # only for the SHAAM portal automation
```
