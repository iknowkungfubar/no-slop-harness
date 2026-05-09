# Agent Operating Rules (CRITICAL)

To maintain a zero-slop environment and maximize token efficiency, all AI agents operating in this repository MUST adhere to the following rules:

1.  **No Hedging:** Never output phrases like "Here is the code," "I have updated the file," or "Please note." 
2.  **No Apologies:** If a tool call fails, do not say "I apologize for the error." Immediately issue the corrected tool call based on the stack trace.
3.  **Context Compaction:** Before finishing a complex task, write a summarized log to `DEVLOG.md` and drop older conversational history.
4.  **Fail Fast:** If you lack the context to complete a file edit safely, do not guess. Abort the sub-task and request clarification via the `escalate_to_coordinator` tool (to be implemented).
5.  **Package Management:** Strictly use `uv` for all Python dependency management. Do not use `pip` directly.
