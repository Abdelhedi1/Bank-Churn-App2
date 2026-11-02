# Ethics and AI usage reflection

## Where AI was used
Claude (Anthropic) was used as a coding assistant to port the Streamlit prototype to Flask, write the database layer, API, pages, tests and documentation, and to render the UML. The student set the requirements (SRS, design), supplied the reference interface, ran the application, and reviewed the output. See `docs/ai-usage-log.md`.

## Risks considered
- **Wrong code or docs**: all output was tested (26 automated tests, 87% coverage) and the interface was run in a real browser; bugs found that way were fixed (see the log). Generated documents still need the student's read-through.
- **Fairness**: the model uses age, gender and country as inputs. These can create unfair treatment of customer groups. Predictions only *suggest* actions and a person decides; nothing is sent automatically (REQ-20). Fairness across groups has not been measured and should be before real use.
- **Privacy**: the dataset is synthetic with no names. Customer ids are masked, relationship managers see only their own customers, and every view/export is audited. Encryption in transit and at rest is not done by the app and must be set at deployment.
- **Over-trust**: scores for customers the model trained on are optimistic (in-sample). The UI shows probabilities, not certainties.
- **Security**: hashed passwords, CSRF protection, security headers. The MCP GitHub token is read from an environment variable only. The demo password is public and must be changed for real use.

## Licenses and IP
Project code is under the repository license. The skills `frontend-design` and `webapp-testing` are Apache-2.0 and keep their LICENSE files. Libraries (Flask, scikit-learn, LightGBM, pandas, Plotly) keep their own licenses. The interface layout follows the student's reference screenshot.
