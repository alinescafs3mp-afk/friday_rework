# Friday

**A personal AI assistant built to run on hardware its owner controls.**

Friday (Пятница) is our effort to build an assistant that can keep track of ongoing work, remember useful preferences, work with files, and help with coding and engineering tasks. We want it to be useful over time, with local model inference and a familiar way to talk to it through Telegram.

There are four of us: **two system administrators and two software developers**. This repository contains the Friday integration, patches, deployment tools, and development records. The project is in active development.

## What we are building

The intended system brings together:

- **Conversation and continuity:** Telegram conversations, persistent history, user preferences, and memory.
- **Practical file work:** creating, revising, and returning useful documents and other artifacts.
- **Coding and engineering:** specialized workers that can carry out tasks and return results to the same conversation.
- **Research:** access to current web sources when a task needs them.
- **Administration:** a web interface for users, access, conversations, tasks, and configuration.

Production model calls are designed to use explicitly configured local endpoints, with no automatic cloud inference fallback. Web research is a separate capability: running the models locally should still allow the assistant to look up information when authorized.

## What has already worked

We have moved beyond a design document. Earlier installed development builds have demonstrated the following in controlled bot-to-bot Telegram tests:

| Area | Observed result |
| --- | --- |
| Conversation | Replies and contextual follow-ups, with the exchanges preserved in native conversation history. |
| Preferences | Saving, updating, and recalling a preference within the tested user's existing conversation. |
| File delivery | TXT and DOCX files received through Telegram, downloaded, and checked against the workspace artifacts. |
| Document revision | A requested date change delivered in a new DOCX copy, with the original preserved and the other document parts unchanged. |

These are specific, bounded observations from earlier builds. They do not establish every document format, memory across fresh sessions, or the reliability of the latest build. The revision test also exposed a technical warning in the document caption that still needs correction.

The [Telegram and document observations](docs/review-candidates/ordinary-telegram-initial-smoke-20261020/README.md) record both the successful results and their limits.

## Current development status

**Status snapshot: 22 October 2026, Moscow time.**

Friday is a development project, and a complete release has not yet been validated. The latest recorded startup attempt failed to establish readiness. A reviewed startup change is awaiting installation after an updater compatibility issue; its effect on startup readiness has not yet been verified. See the [startup and installation status](docs/review-candidates/startup-two-flush-await-bounds-source95-20261022/STATUS.json) for the exact snapshot.

Current work includes startup and update reliability, incoming documents, grounded web research, complete worker workflows, and broader validation of memory, skills, administration, and user isolation. Earlier successful exchanges remain useful evidence; each new installed build still needs its own checks.

## How the system fits together

Friday builds on existing projects. Our work is in their integration, local deployment, access boundaries, task handling, document delivery, and the assistant's behavior.

| Component | Role in the intended system |
| --- | --- |
| [Hermes](https://github.com/NousResearch/hermes-agent) | Main assistant runtime, conversations, memory, ordinary tools, Telegram, and the administrative dashboard. |
| [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) | Dedicated coding worker. |
| [Agent Zero](https://github.com/agent0ai/agent-zero) | Dedicated engineering worker with its own environment and interfaces. |
| Friday integration | The plugin, adapters, patches, local configuration, user and task associations, and result delivery that connect the system. |

The [architecture notes](docs/integration-boundary.md) describe these boundaries. [sources.lock.json](sources.lock.json) records the initial selected upstream revisions; individual development records describe later changes and their validation.

## Hardware and support

Our current development hardware is **one PC with an NVIDIA RTX 5090 and one NVIDIA DGX Spark**.

That lets us develop and test parts of Friday. We want additional inference capacity to evaluate larger local models, longer context, and practical workloads shared by the assistant and its workers. Our current setup limits the scale we can test, even as software integration and reliability work continue.

Our long-term target is an **eight-GPU NVIDIA H200 NVL inference server**. The full configuration we have in mind is now estimated at **over US$900,000 locally**, well beyond what we can fund ourselves. We can make progress toward that target in smaller steps.

If you would like to help, contributions toward hardware, equipment offers, or introductions to someone who might support the project would be welcome. We can share the current results, the proposed configuration, and what we want to test next. You can [get in touch through a repository issue](https://github.com/alinescafs3mp-afk/friday_rework/issues).

## Exploring the repository

| Location | What you will find |
| --- | --- |
| [plugins/friday_rework](plugins/friday_rework/) | Friday's plugin, adapters, administration, access, and task/result handling. |
| [patches](patches/) | Changes to the selected upstream components. |
| [scripts](scripts/), [tools](tools/), [deploy](deploy/) | Preparation, configuration, installation, and deployment tooling. |
| [config](config/) | Assistant personality, research guidance, and runtime policy configuration. |
| [tests](tests/), [validation](validation/) | Component checks, validation tools, and acceptance definitions. |
| [docs](docs/), [analysis](analysis/) | Architecture, implementation notes, dated observations, and development history. |

For technical work, start with:

- [Local model and product configuration](docs/product-profile.md)
- [Installation design and current prerequisites](docs/native-installer.md)
- [Web research and administration requirements](docs/mandatory-web-admin.md)
- [Detailed development status](docs/foundation-status.md)

Deployment currently depends on the selected upstream revisions, reviewed patches, and operator-specific configuration. Read the installation prerequisites before attempting to run the stack.

The detailed logs include unsuccessful attempts and checks that have not run. A passing component test is evidence for that component, rather than a claim that the entire assistant is ready. Each dated record should be read within its stated scope.

The [README before this rewrite](https://github.com/alinescafs3mp-afk/friday_rework/blob/0ad7e023536dd544397011519f8173bb706e88bd/README.md) preserves the earlier checkpoint index.

## Credits and licenses

Friday depends on the work of the Hermes, DeepSeek Harness, and Agent Zero communities, as well as earlier Friday development.

Third-party components retain their own license terms. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the relevant upstream repositories. The third-party notices do not assign a single license to this entire integration repository.
