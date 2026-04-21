# litellm

LiteLLM proxy container. Routes OpenAI-compatible API calls from
Nextcloud (via `integration_openai`) to whatever upstream LLM provider
the customer chose: Anthropic, OpenAI, Bedrock, Vertex, or a chain with
fallbacks.

**Enable** via `AIO_COMMUNITY_CONTAINERS=litellm` in the customer's
`customer.env` (CLAUDE.md §3.6).

Then wire Nextcloud to it via `AI_PROVIDER=litellm` in the same file
(CLAUDE.md §3.10).

## Config file

The container reads `/app/config/config.yaml` at startup. Populate this
from a template in the customer folder:

    customization/customers/<n>/litellm/config.yaml

Example (Anthropic-first with OpenAI fallback):

```yaml
model_list:
  - model_name: claude-sonnet
    litellm_params:
      model: claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY
  - model_name: gpt-4o
    litellm_params:
      model: gpt-4o
      api_key: os.environ/OPENAI_API_KEY

router_settings:
  routing_strategy: simple-shuffle
  fallbacks:
    - claude-sonnet: [gpt-4o]

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
```

## Env vars & secrets

| Var | Purpose | Where to set |
|---|---|---|
| `LITELLM_MASTER_KEY` | Gates all incoming calls; Nextcloud uses this as its `api_key` via `integration_openai`. | Customer secret bundle. |
| `LITELLM_OPENAI_API_KEY` | OpenAI provider key. | Customer secret bundle (optional). |
| `LITELLM_ANTHROPIC_API_KEY` | Anthropic provider key. | Customer secret bundle (optional). |
| `LITELLM_AWS_*` | Bedrock credentials. | Customer secret bundle (optional). |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to a GCP service-account JSON for Vertex. Mount the JSON into `/secrets/gcp-sa.json`. | Customer secret volume. |

Rotate a provider key via `mgmt-ctl litellm rotate <slug> --provider
<openai|anthropic|bedrock|vertex>` (MGMT_CTL_CLI_SPEC.md — reaches
`custom.litellm.rotate_key`, MANAGEMENT_SERVER.md §4.3).

## Integration with Nextcloud

```
customer.env:
  AI_PROVIDER=litellm
  AI_ENDPOINT_URL=http://nextcloud-aio-litellm:4000/v1
  AI_DEFAULT_MODEL=claude-sonnet

customer.env.secret.age:
  AI_API_KEY=<same value as LITELLM_MASTER_KEY>
```

`bootstrap.sh` (§3.10) sets `occ config:app:set integration_openai url|
api_key|default_completion_model_id` accordingly.
