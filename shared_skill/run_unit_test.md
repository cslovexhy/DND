# Running Unit Tests

## Command

```bash
cd /path/to/package && brazil-build single-test -DtestClass={fully.qualified.ClassName} > /tmp/test_output.log 2>&1; echo "EXIT: $?"
```

## Rules

1. **Always save output to a temp file** — never use `tail` or pipe directly. Use `/tmp/` so no zombie files are left in the package.
2. **Check exit code first** — `EXIT: 0` means pass, non-zero means failure.
3. **On failure, grep the log** for relevant errors:
   ```bash
   grep -A3 "FAILED\|AssertionError\|Exception\|Failures (" /tmp/test_output.log | head -50
   ```
4. **For full test output** (e.g., to see assertion details):
   ```bash
   grep -B2 -A10 "expected:.*but was:\|AssertionError" /tmp/test_output.log | head -80
   ```

## Examples

### Run a single test class
```bash
cd ~/workplace/Service/src/ACCCoreLibrary && brazil-build single-test -DtestClass=com.amazon.imdbtv.acc.core.adapters.PoddingEngineAdapterTest > /tmp/test_output.log 2>&1; echo "EXIT: $?"
```

### Run all tests in a package
```bash
cd ~/workplace/Service/src/ACCCoreLibrary && brazil-build single-test > /tmp/test_output.log 2>&1; echo "EXIT: $?"
```

### Check results after run
```bash
# Quick pass/fail summary
grep "Tests run:\|BUILD" /tmp/test_output.log | tail -5

# Find failures
grep -A5 "FAILED\|Failures (" /tmp/test_output.log | head -40
```

## Notes

- `brazil-build single-test` only runs unit tests, not FSUTs
- The `-DtestClass` value is the fully qualified class name (no `.java` extension)
- For running a single method: `-DtestClass=com.example.MyTest#myMethod`
- Build must succeed before tests run — if compilation fails, fix that first

## Debugging Test Failures

1. **Add explicit debug logs** — don't guess. Print intermediate values to stdout (`System.out.println`) to see what's actually happening at runtime.
2. **Avoid Optional chains / method chaining** when writing new code — break into explicit variables so you can log each step. Long `.a().b().c().d()` chains hide which step returned null or an unexpected value.
3. **Run baseline first** — stash your changes (`git stash`), run the test, confirm it passes without your change, then `git stash pop`. This proves whether the failure is yours or pre-existing.
4. **Check test data** — the test's request objects may have fields set that you don't expect (e.g., defaults, builders with pre-populated values). Print the actual object to see what's in it.
