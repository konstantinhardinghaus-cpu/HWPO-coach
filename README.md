# HWPO-coach

A library of reusable [Claude Code](https://claude.com/claude-code) subagents, organized by division. Each agent is a Markdown file with YAML frontmatter (`name`, `description`, `tools`, `model`) plus persona instructions, following Claude Code's [subagent format](https://docs.claude.com/en/docs/claude-code/sub-agents).

## Divisions

| Division | Agents |
| --- | --- |
| `engineering/` | `frontend-developer`, `backend-developer`, `fullstack-developer`, `mobile-developer`, `devops-engineer`, `qa-engineer` |
| `design/` | `ui-designer`, `ux-researcher`, `brand-designer` |
| `product/` | `product-manager`, `business-analyst` |
| `marketing/` | `content-strategist`, `seo-specialist`, `social-media-manager` |
| `operations/` | `project-manager`, `technical-writer` |

## Install

Install all agents to your Claude Code directory:

```bash
./scripts/install.sh --tool claude-code
```

Install only specific divisions:

```bash
./scripts/install.sh --tool claude-code --categories engineering,design
```

Or manually copy a division if you only want one:

```bash
cp engineering/*.md ~/.claude/agents/
```

Then activate any agent in your Claude Code sessions:

```
"Hey Claude, activate Frontend Developer mode and help me build a React component"
```

## Adding a new agent

1. Pick (or create) a division directory.
2. Add a `<agent-name>.md` file with frontmatter:

   ```markdown
   ---
   name: agent-name
   description: Use this agent when... Examples: "...", "...".
   tools: Read, Write, Edit, Glob, Grep
   model: sonnet
   ---

   You are a senior ... who specializes in ...

   ## Approach
   - ...

   ## When implementing
   1. ...
   ```

3. Re-run `./scripts/install.sh --tool claude-code` to pick it up.
