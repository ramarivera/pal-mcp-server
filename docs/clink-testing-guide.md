# Testing PAL MCP Server Clink Integration

This guide describes how to test the PAL MCP server's `clink` tool with different CLI integrations. As a running Claude instance (e.g., `claude-rar`), you can invoke external AI CLIs through PAL's clink functionality.

## Prerequisites

1. **PAL MCP Server running** with clink tool enabled
2. **CLI clients configured** in either:
   - `conf/cli_clients/*.json` (builtin)
   - `~/.pal/cli_clients/*.json` (user custom)

## Available CLI Clients

Check available clients by asking PAL to list them, or inspect the registry:

```
Available clients: claude, codex, gemini, cursor, claude-rar, minimax, glm
```

---

## Test Case 1: Cursor Agent CLI

The `cursor` CLI integrates with Cursor's AI agent. It uses a custom parser (`cursor_json`) to handle Cursor's response format.

### How to Test

Use the PAL MCP `clink` tool with:

```json
{
  "cli_name": "cursor",
  "prompt": "Explain what a Python context manager is in 2-3 sentences.",
  "role": "default"
}
```

### Expected Behavior

1. PAL invokes: `cursor <internal_args> <config_args>`
2. The prompt is sent via stdin to the cursor CLI
3. Cursor processes the request and returns JSON output
4. PAL's `CursorJSONParser` extracts the response content
5. You receive the AI response through PAL

### Validation Points

- [ ] CLI executes without timeout errors
- [ ] Response is properly parsed (not raw JSON)
- [ ] Content is coherent and answers the prompt
- [ ] No parser errors in PAL logs

---

## Test Case 2: Nocode Custom CLI (minimax example)

Custom CLIs like `minimax` demonstrate the **config-only CLI support** feature. These are defined purely through JSON configuration without any code changes to PAL.

### Configuration Structure

The `minimax` CLI is configured in `~/.pal/cli_clients/minimax.json`:

```json
{
  "name": "minimax",
  "command": "nu",
  "parser": "builtin:claude_json",
  "runner": "builtin:claude",
  "internal_args": ["--login", "-c", "minimax --output-format json --permission-mode acceptEdits"],
  "additional_args": [],
  "roles": {
    "default": {
      "prompt_path": "systemprompts/clink/default.txt"
    }
  }
}
```

**Key points:**
- `command`: Just `nu` (nushell executable)
- `internal_args`: Contains the full nushell login invocation with the alias
- `parser`/`runner`: Uses builtin Claude implementations via spec strings

### How to Test

Use the PAL MCP `clink` tool with:

```json
{
  "cli_name": "minimax",
  "prompt": "What is 2 + 2? Reply with just the number.",
  "role": "default"
}
```

### Expected Behavior

1. PAL invokes: `nu --login -c "minimax --output-format json --permission-mode acceptEdits"`
2. Nushell loads login config, resolves the `minimax` alias
3. The alias (a claude wrapper with specific env vars) executes
4. Response flows back through PAL's ClaudeJSONParser
5. You receive the AI response

### Validation Points

- [ ] Nushell login shell resolves the alias correctly
- [ ] Environment variables from the alias are applied
- [ ] Claude JSON output is properly parsed
- [ ] Response matches expected behavior for that model/config

---

## Test Case 3: Cross-CLI Comparison

Test the same prompt across multiple CLIs to verify consistent behavior:

### Prompt

```
Explain recursion in programming in exactly one sentence.
```

### Test Matrix

| CLI | Command |
|-----|---------|
| `claude` | Builtin claude CLI |
| `cursor` | Cursor agent |
| `minimax` | Nocode custom (nushell alias) |
| `glm` | Nocode custom (nushell alias) |

### How to Execute

Run each sequentially:

```json
{"cli_name": "claude", "prompt": "Explain recursion in programming in exactly one sentence."}
{"cli_name": "cursor", "prompt": "Explain recursion in programming in exactly one sentence."}
{"cli_name": "minimax", "prompt": "Explain recursion in programming in exactly one sentence."}
```

### Expected Results

- All CLIs should return coherent one-sentence explanations
- Response times may vary based on underlying model
- Parser should handle each CLI's output format correctly

---

## Troubleshooting

### Common Issues

1. **"Executable not found"**
   - Ensure the CLI binary is in PATH
   - For nushell aliases: verify `nu --login -c "which <alias>"` works

2. **"Parser error"**
   - Check if the CLI outputs the expected format
   - Verify `parser` spec matches the CLI's output format

3. **"Timeout"**
   - Increase `timeout_seconds` in the CLI config
   - Check if the underlying CLI is responsive

4. **Nushell alias not found**
   - Ensure alias is defined in nushell's login config
   - Test with: `nu --login -c "<alias> --help"`

### Debug Commands

Check PAL logs:
```bash
tail -f logs/mcp_server.log | grep -i clink
```

Verify CLI config loaded:
```python
from clink.registry import get_registry
registry = get_registry()
print(registry.list_clients())
```

---

## Adding New Custom CLIs

To add a new CLI without code changes:

1. Create `~/.pal/cli_clients/<name>.json`
2. Specify required fields:
   - `name`: Unique identifier
   - `command`: Executable (e.g., `nu` for nushell wrappers)
   - `parser`: `builtin:<name>` or `path/to/parser.py:ClassName`
3. Optional fields:
   - `runner`: Agent spec (defaults to `BaseCLIAgent`)
   - `internal_args`: System args (include full command for shell wrappers)
   - `roles`: Role-specific prompts and args

### Example: Adding a new nushell alias wrapper

```json
{
  "name": "my-custom-claude",
  "command": "nu",
  "parser": "builtin:claude_json",
  "runner": "builtin:claude",
  "internal_args": ["--login", "-c", "my-alias --output-format json"],
  "roles": {
    "default": {"prompt_path": "systemprompts/clink/default.txt"}
  }
}
```

Reload PAL MCP server to pick up the new config.
