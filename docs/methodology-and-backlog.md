# Methodology and backlog

## Choice: Scrum, 2-week sprints (individual project)
Reason: one developer, fixed course deadline, requirements already stable (SRS), so two-week sprints (the recommended length for small teams) with a demo at each end reduce risk. Kanban was rejected because there is no continuous flow of changes. Estimates are T-shirt sizes by the developer; AI helped draft them and the student must validate them.

## Requirements elicitation (AI-assisted)
The stories below were drafted by the AI assistant (Claude) from the Lab 2 SRS, after the student's request: *"okey i want you know to go throught the requirement and the design ..."* (full text in `docs/ai-usage-log.md`, row 5). The instructor's template prompt ("Act as a product analyst...") was not used. The student still has to validate the stories and priorities with a peer or the instructor.

| ID | User story | Acceptance criteria | MoSCoW | Size |
|---|---|---|---|---|
| US1 | As an RM I see churn probability for a customer | Probability, tier and top reasons shown; invalid input rejected | Must | M |
| US2 | As an RM I only see my customers | Other branches return no data | Must | M |
| US3 | As a retention manager I get alerts for high risk | Alert raised at threshold after each scoring run | Must | M |
| US4 | As an admin I upload data and train models | Two models compared, best AUC active | Must | L |
| US5 | As an admin I run weekly scoring | Runs automatically, one run on 6,000+ customers in seconds | Must | M |
| US6 | As an executive I see a monthly KPI report | Report page and CSV | Should | S |
| US7 | As a manager I log retention actions | Action stored; nothing sent to customer | Should | S |
| US8 | As an auditor I can see who viewed customer data | View/export/login logged, ids masked | Must | S |
| NFR1 | Passwords hashed, CSRF protection, role checks | Tests cover 401/403 | Must | S |
| NFR2 | Scoring and page responses are fast | Scoring time recorded per job | Should | S |
| NFR3 | Encryption in transit and at rest | Done at deployment (not in app) | Could | M |

## Sprints
1. Data and model: dataset, features, training, metrics.
2. Backend: store, auth, scoring, alerts, API, tests.
3. Interface: dashboard and pages from the reference design.
4. Docs, UML, AI log, refactor report, demo.
