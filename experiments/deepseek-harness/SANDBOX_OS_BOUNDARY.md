# Twelfth knife — external official DeepSeek Harness Linux OS containment test

This is an **optional, experimental Docker smoke**, not a production runtime,
not a new Vera agent, and not a security certification of DSH's built-in tools.

## What is actually executed

CI installs the pinned **official** `@deepseek-ai/dsh@0.2.0-rc.2` in an
ephemeral directory. A minimal Node 24 / Python 3 / Bash image is built from
an **empty Docker build context**, with **no COPY instruction**, no Git checkout
in the image. Only the preinstalled DSH runtime plus a minimal COPY of the
existing TRISYNORA read-only MCP bridge, overlay and synthetic test driver
are bind-mounted READ-ONLY. **No Vera, H3 or PointFlux Git checkout, secret,
service socket or host home directory enters the container.**

The real DSH Headless Agent runs within that container, invokes the genuine
Python stdio MCP plug-in with a local mock model provider, and the second
model request must contain the MCP tool result.

The **same running container** also executes hostile file, shell and process
probes against synthetic *host-only* canary paths. These are deliberately
test-only paths: no actual user secret or original product repository is read.

Expected Linux Docker command properties:

- `--network=none`: an external internet IP and the runner-host's local-only
  test TCP listener must BOTH be unreachable from the separate network
  namespace, while the container's own 127.0.0.1 mock provider remains usable.
- `--read-only` and a bounded `--tmpfs /tmp`: test writes to the root
  filesystem and to the source read-only bind mount MUST fail.
- `--cap-drop=ALL`, `--security-opt=no-new-privileges`,
  `--user=10001:10001`, `--pids-limit=96`, bounded memory/CPU.
- `--mount ...readonly` **only** for the pinned runtime and minimal
  scratch-staged driver/plugin; all other Docker mounts, extra environment
  variables, host networking, host PIDs, Docker socket and privileged switches
  are rejected by `sandbox/contract_gate.py`.
- An actual Bash subprocess, Python filesystem access and `/proc/1` identity
  check run inside that same sandbox, with no host-only file readable and no
  bind-mount mutation.

The launch-only hardening gate has deliberately adversarial Python tests
(`test_dsh_sandbox_policy.py`): it fails if an unsafe Docker flag, additional
mount, writable source, privileged mode, host PID/network or inherited host
credential is introduced. The actual container probe `sandbox/container_sandbox_probe.py`
must ALSO pass with the pinned Headless Agent/MCP invocation in the same
namespace. The runner is `sandbox/smoke_docker_sandbox.py`.

Run only on an **ephemeral Linux GitHub runner with Docker available**, with
the pinned official DSH installed into runner temp. The real CI includes this
as a required step in the pinned-harness-web job.

## Important limitations: DO NOT OVERCLAIM

- The Shell and Python file APIs exercised are **real processes in the same
  container**; the test also boots and exercises real DSH Agent→MCP in that
  container. **It does not force-call every stock DSH model-facing `bash`,
  `read`, `write`, `edit` or process tool.** Its Docker OS boundary
  applies to all container processes, but this test does not certify those
  tool implementations or their own policy/escalation semantics.
- The agent's Headless test uses a **keyless localhost scripted provider**,
  not an external real model provider, and no native product is connected.
  The Chromium Web tests continue as separate sandboxed GitHub runner steps,
  **not** in this Docker container. Do NOT advertise Web UI confinement as
  proven by this test.
- This tests one GitHub Ubuntu Docker configuration. It is **not** Windows
  isolation proof, VM escape/power-loss proof, malicious kernel attack
  resilience, syscall/seccomp test, or a full runtime authority audit.
- Docker build downloads the official Node image and Debian dependencies
  over the GitHub runner network; that setup is NOT the agent runtime.
  The actual DSH container is launched **networkless**. The GitHub build
  supply chain and environment still need pinning/digest audit before any
  production deployment.
- The staged bridge and official package are mounted read-only, but the
  agent is allowed to write to its own ephemeral `/tmp` for Sessions and
  the inner mock. That never authorizes writes to native products.
- The policy gate cannot prevent an attacker who controls the host Docker
  daemon, the runner before launch, or the mounted trusted runtime from
  changing the effective sandbox. It is a CI proof of the checked launch
  configuration, not a replacement for a host/VM threat model.

**No native repository modifications, no merge, no fourth MCP tool, no
Harness-native Jobs mirror, no native execution permission.**
