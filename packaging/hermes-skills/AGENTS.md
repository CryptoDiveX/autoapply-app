<!-- hermes-runtime-execution-policy-v1 -->
## Hermes runtime execution boundary

1. Run host operations through Hermes tools, Profile Hub, or Hermes Agent Runtime.
2. Never use standalone inline host interpreters such as `python -c`, `python3 -c`, `node -e`, or equivalent inline-eval shortcuts for routine work.
3. Prefer Hermes `execute_code`; run durable Python files with `/Applications/Hermes Agent Runtime.app/Contents/MacOS/Hermes` when macOS/protected access is involved.
4. OpenClaw and other orchestrators must dispatch host execution into Hermes/Profile Hub/Runtime first.
5. Do not ask the user to approve routine raw inline-eval when the approved runtime can perform the operation.
6. If the approved runtime is unavailable, stop and report the blocker instead of bypassing the boundary.
<!-- /hermes-runtime-execution-policy-v1 -->
