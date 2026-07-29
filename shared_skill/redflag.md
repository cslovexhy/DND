# Red Flags — Things NOT To Do

## 1. Never use `brazil-build` or `brazil-build release`

**ONLY use `brazil-build build` or `brazil-build single-test`.**

- `brazil-build release` runs the full release pipeline (compile + static analysis + ALL tests) which takes 10+ minutes and is wasteful during development.
- `brazil-build build` compiles the code — use this to verify changes compile.
- `brazil-build single-test -DtestClass=...` runs a specific test — use this to verify test changes.
- `brazil-build test` in **MarioService** runs unit tests only (skips FSUTs) — use this to validate schema changes (e.g., `BackwardsCompatibilityTest` after modifying `PASExecutionJavaTypes` models).

```bash
# ✅ Correct — compile only
brazil-build build > /tmp/build.log 2>&1; echo "EXIT: $?"

# ✅ Correct — run a specific test
brazil-build single-test -DtestClass=com.example.MyTest > /tmp/test.log 2>&1; echo "EXIT: $?"

# ✅ Correct — MarioService unit tests (fast, validates schema compatibility)
cd ~/workplace/ParisDevelopment/src/MarioService && brazil-build test > /tmp/mario_test.log 2>&1; echo "EXIT: $?"

# ❌ NEVER do this
brazil-build release
brazil-build
```

## 2. Always add/update tests for new code

Every new or modified production code must have corresponding unit test coverage. Do NOT submit code without tests.

- New methods/classes → new test cases
- Modified behavior → update existing tests or add new ones to cover the change
- Goal: maintain coverage, prevent regressions

## 3. Always run `brazil-build format-fix` for ACCCoreLibrary

After modifying any code in `ACCCoreLibrary`, run the formatter before committing:

```bash
cd ~/workplace/ParisDevelopment/src/ACCCoreLibrary && brazil-build format-fix
```

This ensures consistent code style and avoids noisy formatting diffs in CRs.

## 4. Never commit before build and tests pass

Do NOT run `git commit` until:
- The package builds successfully (`brazil-build build` exits 0)
- Relevant unit tests pass (`brazil-build single-test`)
- If the build has pre-existing failures unrelated to your change, explicitly confirm with the user before committing

Committing broken code creates noise in git history and forces amends/reverts. Always verify first.

## 5. Avoid method chaining (`.a().b().c().d()`) in production code

Write explicit intermediate variables instead of long chains. Reasons:
- **Debugging**: Can't add log statements between chained calls
- **Null safety**: Hard to tell which call in the chain returned null
- **Readability**: Each step is named and self-documenting

Bad:
```java
final String value = Optional.ofNullable(requestItem.getSpec())
    .map(spec -> spec.getPlacement())
    .map(p -> p.getExt())
    .map(ext -> ext.getResponsefmt())
    .orElse(null);
```

Good:
```java
final var spec = requestItem.getSpec();
final var placement = (spec != null) ? spec.getPlacement() : null;
final var ext = (placement != null) ? placement.getExt() : null;
final String responseFmt = (ext != null) ? ext.getResponsefmt() : null;
```

The second form lets you add a log/breakpoint at any step and immediately see which value is unexpected.

## 6. Always show progress for batch operations

When running scripts that iterate over multiple items (deploying dashboards, authing to accounts, processing files), **ALWAYS print progress to stdout with `flush=True`** so the user can see it's working.

```python
# ✅ Correct — progress visible immediately
for i, item in enumerate(items, 1):
    # ... do work ...
    print(f"[{i}/{total}] ✅ {item}", flush=True)

# ❌ NEVER do this — user sees nothing until script finishes (or gets cancelled)
for item in items:
    # ... do work silently ...
pass
```

Rules:
- Print `[N/total]` prefix so user knows position
- Use ✅/❌/⏭️ emoji for instant visual status
- Use `flush=True` on every print (Python buffers stdout in non-TTY mode)
- Print auth steps separately so user can see when it's waiting on network

## 7. Never use the `knowledge` tool to find local files

When the user says "read the worklog" or "check the file," **look at the current directory first** (`pwd`, `ls`). Do NOT search the knowledge base index — it may point to an unrelated project.

Rules:
- Always check pwd and list files in the current directory before searching elsewhere
- The user's instruction to "check pwd" means the relevant file is HERE, not in some indexed knowledge base
- Knowledge bases persist across sessions and may contain stale/irrelevant entries from other projects
- If a file exists in the current directory or an obvious nearby path, read it directly — don't semantic-search for it
- Never create or auto-populate knowledge base entries without explicit user request

```bash
# ✅ Correct — check what's here first
pwd
ls *.md

# ❌ NEVER do this when told to "read the worklog"
knowledge search "build slowness"  # wrong — may find unrelated project
```

## 8. Never use `cr --all` — always use explicit `-i` package list

**Problem:** `cr --all` includes ALL modified packages in the workspace, which can accidentally pull in packages with unrelated local changes (e.g., ACCInternalModels or other packages with WIP/stashed changes). This has caused issues before.

**Rule:** Always use `cr -i` to explicitly list the packages that belong on the CR.

```bash
# ✅ Correct — explicit package list
cr -r CR-291765142 -i "ACCCoreLibrary,MarioService,PASExecutionJavaTypes,PDECoreLibrary,PDEInternalModels,PDESharedDaggerModules"

# ❌ NEVER do this
cr -r CR-291765142 --all   # may include unrelated packages with local changes
cr --all                    # same problem for new CRs
```
