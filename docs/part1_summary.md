# C5 Part 1: MCP and the Fetch Server

## What the article explains

LLMs are capable, but on their own they are cut off from the files and services people actually use. Before MCP, every model-tool connection needed its own custom integration, which was brittle and hard to scale. Anthropic released MCP in November 2024 as an open standard that turns this N×M problem, with every agent wired to every tool, into an N+M one: each tool is wrapped once as a server, and any compatible agent can use it.

MCP splits the system into three roles. The **host** is the AI application the user works in, such as Claude Desktop or an IDE. The host runs one **client** per connection, and each client talks to exactly one **server**, a separate program that exposes capabilities. The client discovers those capabilities at runtime instead of having them hard-coded. Servers offer three kinds: tools, which the model chooses to call; resources, which the application provides as context; and prompts, which the user invokes. This split of control turned out to matter in real server code.

## Critiquing the Fetch server

The Fetch server exposes one `fetch` tool and one `fetch` prompt. Its **interface is well defined**: every argument is typed, documented and bounded, and strict validation rejects `"10"` where a number is expected instead of silently converting it.

**Isolation** is less clear-cut. Behind that single tool, the server checks robots.txt, blocks private IP addresses on every redirect, decodes the page, converts HTML to Markdown and paginates the result. By the "and" test this is too many jobs, but I think the bundling is justified. Raw HTML is not useful to the model, so splitting fetching from conversion would only push large pages through its context.

**Predictability** is where I found the weak spots. Expected failures, like a robots.txt refusal or an unreachable URL, are raised as clear `ToolError`s, and truncated output tells the model which `start_index` to continue from. However, a page that fails to simplify comes back as a successful result with an `<error>` tag inside the text, so the model must read the text to notice. The tool description also says nothing about truncation or robots.txt, which is the usability risk the article warns about: a model can only use a tool as well as its description explains it.

Finally, the server connects back to the article. The model-controlled tool respects robots.txt, while the user-controlled prompt skips it, because a person explicitly asked for that page.

## References

- Ksenia Se, "What Is MCP, and Why Is Everyone – Suddenly! – Talking About It?", Hugging Face blog: https://huggingface.co/blog/Kseniase/mcp
- Fetch MCP server, Model Context Protocol servers repository: https://github.com/modelcontextprotocol/servers/tree/main/src/fetch
