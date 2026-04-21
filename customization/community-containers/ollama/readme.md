# ollama

Local LLM runner. Exposes an OpenAI-compatible `/v1` API on port 11434
(internal network only) that Nextcloud's `integration_openai` app can
point at.

**Enable** via `AIO_COMMUNITY_CONTAINERS=ollama` in the customer's
`customer.env` (CLAUDE.md §3.6).

**Wire Nextcloud to it** via `AI_PROVIDER=ollama` +
`AI_ENDPOINT_URL=http://nextcloud-aio-ollama:11434/v1` in the same file
(CLAUDE.md §3.10).

## Hardware requirements

Local inference is RAM-heavy and ideally GPU-accelerated:

- **CPU-only, ≤8 GB RAM** — usable only for very small models
  (Phi-3-mini, Llama-3.2-1B). Latency is seconds-per-token.
- **CPU-only, 16+ GB RAM** — Llama-3.1-8B-Instruct at ~1-2 tok/s.
- **GPU (Intel Arc / AMD ROCm / NVIDIA)** — this container exposes
  `/dev/dri` for Intel/AMD integrated and discrete GPUs. For NVIDIA, set
  `NEXTCLOUD_ENABLE_NVIDIA_GPU=true` at the AIO level (the runtime flag
  has to be enabled on the host, not here).

If the customer's host does not meet these, steer toward `AI_PROVIDER=openai`
or `AI_PROVIDER=litellm` pointed at a cloud provider.

## Env vars

| Var | Default | Purpose |
|---|---|---|
| `OLLAMA_KEEP_ALIVE` | `5m` | How long to keep models loaded after last use. |
| `OLLAMA_NUM_PARALLEL` | `2` | Concurrent request slots. |
| `OLLAMA_MAX_LOADED_MODELS` | `1` | More eats more RAM; raise with care. |

## Pulling models

Models must be pulled explicitly before use:

    mgmt-ctl ollama pull <slug> llama3.1:8b-instruct-q4_K_M

(MGMT_CTL_CLI_SPEC.md — reaches the agent's `custom.ollama.pull`
command kind, MANAGEMENT_SERVER.md §4.3.)

## Integration with Nextcloud

```
customer.env:
  AI_PROVIDER=ollama
  AI_ENDPOINT_URL=http://nextcloud-aio-ollama:11434/v1
  AI_DEFAULT_MODEL=llama3.1:8b-instruct-q4_K_M
```

`bootstrap.sh` (§3.10) does not set an `AI_API_KEY` for Ollama — the
local endpoint doesn't require one.

## Known gotchas

- **Cold start** — first request after `OLLAMA_KEEP_ALIVE` expires pays
  model-load latency (seconds). Nextcloud's Assistant shows a spinner;
  this is expected.
- **OOM kills** — if the model doesn't fit, ollama will get killed by
  the kernel's OOM reaper. `mgmt-ctl logs <slug> --container
  nextcloud-aio-ollama` will show `out of memory`; pick a smaller quant
  (`q2_K`, `q3_K`) or rightsize the host.
- **GPU passthrough on Proxmox/KVM** — requires VFIO setup on the host
  and is out of scope for this container.
