# AI usage log

Tool: Claude (Claude Code / Claude app). Output flagged as **direct** = used with little change; **edited** = changed after review or testing.

| Date | Prompt (summary, by the student) | Output | Flag |
|---|---|---|---|
| 2026-10 | Read the Lab 6 files, build it as a real website (not Streamlit), give a GitHub repo | Flask port of the prototype, repo layout | edited (data columns, errors fixed after running) |
| 2026-10 | Make a dataset like Churn_Modelling with credit score, products, card, active, salary, country; later "make it 8000 clients" | 8,000-row dataset | edited (sampling bug 7,999 rows fixed) |
| 2026-10 | Write the CRISP-DM documentation | `docs/crisp-dm.md` | direct, to be reviewed |
| 2026-10 | Go through the requirements (Lab 2) and design (Lab 5) and use the Skills/MCP PDF | Roles, audit, alerts, scoring, reports, skills, MCP configs | edited |
| 2026-10 | Make the interface look like my dashboard screenshot | Dark theme, pages, charts | edited (chart axes, drawer bugs fixed after browser run) |
| 2026-10 | Work the missing parts of the instructor checklist | UML (Mermaid), OpenAPI, guides, reports | direct, to be reviewed |

Bugs the AI introduced and that testing caught: missing-column crash in data summary, wrong id type when adding an action, UI saying "training complete" before scoring finished, trend chart axes. Prompts were not saved word for word; the table summarizes them.

**Student to complete**: exact prompt text from your own chat history for the requirements step (section A of the guidance).
