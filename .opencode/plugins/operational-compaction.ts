import type { Plugin } from "@opencode-ai/plugin"
import { join } from "node:path"

export const OperationalCompaction: Plugin = async ({
  directory,
  client,
}) => {
  return {
    "experimental.session.compacting": async (input, output) => {
      const statePath = join(directory, "AGENT_STATE.md")

      let authoritativeState = ""

      try {
        const stateFile = Bun.file(statePath)

        if (await stateFile.exists()) {
          authoritativeState = await stateFile.text()
        }
      } catch (error) {
        await client.app.log({
          body: {
            service: "operational-compaction",
            level: "warn",
            message: "Could not read AGENT_STATE.md",
            extra: {
              statePath,
              error: String(error),
            },
          },
        })
      }

      const stateBlock = authoritativeState.trim()
        ? `
<authoritative-operational-state>
The following file is authoritative. Preserve every still-valid item
verbatim in the Operational Checkpoint section. Never silently omit,
reinterpret, or contradict it.

Source: ${statePath}

${authoritativeState.trim()}
</authoritative-operational-state>
`
        : `
<authoritative-operational-state>
No AGENT_STATE.md file was found.

Extract the operational state from the conversation history. Do not
invent completed, failed, prohibited, or pending actions.
</authoritative-operational-state>
`

      output.prompt = `
Create a continuation checkpoint from the conversation history.

The checkpoint will replace older active context. Missing operational
facts can cause the next agent to repeat destructive or failed actions.
Completeness of operational state is more important than brevity.

MANDATORY RULES

1. Preserve explicit user instructions that are still active.
2. Preserve every attempted action and its result.
3. Preserve failed actions, including why they failed.
4. Preserve all actions marked "do not repeat", prohibited, unsafe,
   destructive, invalid, or already completed.
5. Preserve pending actions and the exact mandatory next action.
6. Preserve exact paths, commands, identifiers, error messages, version
   numbers, tool results, and relevant numeric values.
7. Never change an action from pending to completed without evidence.
8. Never infer that a task succeeded merely because files were created.
9. Never omit operational state because another project task appears
   more prominent or recent.
10. When facts conflict, retain the latest explicit user-provided state
    and record the conflict under Uncertainties.
11. Do not provide new advice or continue the task.
12. Do not mention the summarization or compaction process.
13. Use the same language as the conversation.
14. Every section below is mandatory. Write "(none)" when truly empty.

OUTPUT EXACTLY THIS STRUCTURE

## Objective
- Current requested outcome.

## Active Constraints
- User instructions and restrictions that remain active.
- Required output formats and acceptance criteria.

## Operational Checkpoint

### Completed Actions
- Action:
  - Result:
  - Evidence:

### Failed Actions
- Action:
  - Failure:
  - Evidence:

### Prohibited or Do Not Repeat
- Action:
  - Reason:

### Pending Actions
- Action:
  - Status:

### Mandatory Next Action
- Exactly one next action, or "(none)" when the user has not defined one.

## Important Decisions
- Decisions already made and their rationale.

## Evidence and Tool Results
- Relevant tool calls and exact results.
- Preserve failed and destructive results, not only successful ones.

## Files and Artifacts
- Exact path:
  - Current state:
  - Modified, created, deleted, or missing:

## Current Work State
### Active
- Current unfinished work.

### Blocked
- Blockers and missing information.

## Next Move
1. First valid next step.
2. Additional steps only when already supported by the conversation.

## Uncertainties
- Conflicts, missing data, and facts that must not be assumed.

${stateBlock}
`.trim()

      await client.app.log({
        body: {
          service: "operational-compaction",
          level: "info",
          message: "Operational compaction prompt installed",
          extra: {
            sessionID: input.sessionID,
            statePath,
            stateLoaded: Boolean(authoritativeState.trim()),
            stateLength: authoritativeState.length,
          },
        },
      })
    },
  }
}
