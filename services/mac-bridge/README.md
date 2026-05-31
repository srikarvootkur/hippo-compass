# Mac Bridge

Future local-only bridge for Mac-specific integrations such as iMessage.

This service should run on the Mac, not on Hetzner. It should sync only approved message metadata, summaries, and writing-style examples to the assistant API.

Rules for v1:

- Do not send iMessages automatically.
- Do not expose the local Messages database to the public internet.
- Use explicit allowlists for conversations.
- Queue drafted replies for approval.
- Keep raw sensitive message content local unless explicitly approved.
