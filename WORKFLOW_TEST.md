# Workflow Test — Smart Farm Workspace

This file is a short test note describing how the Smart Farm tools fit together.

## How the pieces work together

- **Coder** provides the cloud development workspace (`/home/coder`). It hosts the
  cloned repositories (such as `my-farm-advisor-skills`) and gives the agent a
  consistent, pre-provisioned Linux environment to work in.
- **OpenCode** is a coding agent running inside that Coder workspace. It reads
  the repository, makes edits, runs shell commands, and develops and maintains
  the skills catalog (farm advisory, breeding trials, QTL analysis).
- **Hermes** is an independent agent running in the same Coder workspace. It is
  a peer of OpenCode, not a routing layer: OpenCode handles coding and skill
  development, while Hermes handles general questions and running the
  existing skills.
- **Hermes and OpenCode are not connected in a chain.** They are two
  independent agents that happen to share the same Coder workspace and its
  tools; prompts from the user do not flow from one into the other.
- **GitHub** is the source of truth. Each workspace has remotes for the personal
  fork (`origin`) and the canonical upstream repository; changes made by OpenCode
  are committed, pushed to `origin`, and shared via pull requests back to
  `upstream`.

## Flow

1. A request arrives in the Coder-hosted workspace and is answered by either
   Hermes (general questions, running skills) or OpenCode (coding, skill
   development) — the two operate independently.
2. OpenCode works on files locally, following the repo's AGENTS.md conventions.
3. Changes are validated (`./scripts/validate.sh`) and committed.
4. The commit is pushed to GitHub (`origin`) and proposed upstream.

---
*Created as a workflow test file only; no other repository files were modified.*
