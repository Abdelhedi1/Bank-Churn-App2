# CRISP-DM Documentation — Churn Detection Pro

This document describes the project following the six phases of **CRISP-DM**
(Cross-Industry Standard Process for Data Mining). Every number below was
produced by running the code in this repository on the bundled dataset
(`data/Bank Customer Churn Prediction.csv`, 8,000 customers) with a fixed random
seed (`42`). Re-running the project gives the same numbers.

| # | Phase | Where it lives in the project |
|---|-------|-------------------------------|
| 1 | Business Understanding | Sections below, `AI_CONTEXT.md`, the Lab 2/3 SRS |
| 2 | Data Understanding | **Data** page, `app/ml.py::load_csv` |
| 3 | Data Preparation | **Features** page, `app/ml.py` (cleaning, features, encoding, split, scaling) |
| 4 | Modeling | **Training** page, `app/ml.py::train_*` |
| 5 | Evaluation | **Training** page (metrics, ROC, confusion matrices) |
| 6 | Deployment | **Prediction** page, Flask API, `run.py` |

CRISP-DM is iterative: findings in later phases sent us back to earlier ones
(see "Iterations" at the end).

---

## 1. Business Understanding

### 1.1 Business problem
A bank loses revenue when customers close their accounts or stop using its
products (**churn**). Winning a new customer costs more than keeping an existing
one, so the retention team wants to know **which customers are most likely to
leave** while there is still time to contact them with an offer.

### 1.2 Business objective
Give bank analysts a tool that, from customer data, estimates each customer's
probability of churning, so the retention team can focus effort on the
highest-risk customers.

### 1.3 Data-mining goal
Build a **binary classifier** that predicts `churn` (1 = the customer left,
0 = stayed) and outputs a probability. The probability is turned into a risk
level:

| Risk level | Churn probability |
|------------|-------------------|
| Low | below 30% |
| Medium | 30% to below 60% |
| High | 60% or more |

### 1.4 Success criteria used in this project
- The model must rank churners above non-churners clearly better than chance:
  judged mainly by **ROC AUC** (0.5 = random, 1.0 = perfect) and **KS**.
- Because churners are the minority (about 1 in 5), accuracy alone is not
  enough. We also report **precision, recall and F1** for the churn class.
- The result must be usable without writing code: a web app for single and
  batch scoring.

> The formal functional requirements (REQ-01 to REQ-20) are in the team's SRS
> from Lab 2. No numeric acceptance target (for example "AUC above 0.80") was
> defined in the material available for this document — **TODO (team):** add one
> if your SRS defines it.

### 1.5 Assets, constraints and risks
- **Data:** the public *Churn_Modelling* dataset (10,000 customers); this project
  uses an 8,000-customer sample.
- **Tools:** Python 3.12+, Flask, pandas, scikit-learn, imbalanced-learn,
  LightGBM, Plotly.js.
- **Constraints:** no real bank data is committed; names are removed.
- **Risks:** the model is only as good as the data. It was trained on one
  dataset with three countries; results on another bank's customers are unknown.

---

## 2. Data Understanding

### 2.1 Source and collection
`Churn_Modelling.csv` has 10,000 rows and 14 columns. The project uses a
**stratified random sample of 8,000 rows** (seed 42, stratified on country and
churn) so that the churn rate and country mix stay the same as the full file:

| | Full file (10,000) | Sample (8,000) |
|---|---|---|
| Churn rate | 20.37% | 20.37% |
| France / Germany / Spain | 50.1% / 25.1% / 25.1% | 50.1% / 25.1% / 24.8% |
| Male / Female | 54.6% / 45.4% | 54.2% / 45.8% |

Only a sample of **real** rows is used. No customers were invented.

### 2.2 Data description
Final schema after renaming (12 columns, 8,000 rows):

| Column | Type | Meaning |
|--------|------|---------|
| `customer_id` | integer | Customer identifier (dropped before modeling) |
| `credit_score` | integer | Credit score (350–850) |
| `country` | text | France, Germany or Spain |
| `gender` | text | Male / Female |
| `age` | integer | Age in years (18–92) |
| `tenure` | integer | Years as a customer (0–10) |
| `balance` | float | Account balance (0–250,898) |
| `products_number` | integer | Number of bank products (1–4) |
| `credit_card` | 0/1 | Has a credit card |
| `active_member` | 0/1 | Active member |
| `estimated_salary` | float | Estimated salary (11.58–199,992) |
| `churn` | 0/1 | **Target**: 1 = left the bank |

Columns removed from the original file: `RowNumber` (a counter, no information)
and `Surname` (personal data, not needed).

### 2.3 Data quality checks
Missing values, duplicates and ranges were checked on the full 10,000-row file; the zero-balance share is measured on the 8,000-row sample.
- **Missing values:** 0.
- **Duplicate customer IDs:** 0. **Duplicate rows** (ignoring ID/name): 0.
- **Ranges:** all values are plausible (credit score 350–850, tenure 0–10,
  products 1–4, binary columns only 0/1).
- **Notable pattern:** 36.1% of the sampled customers have a balance of exactly 0. This is
  real, not missing data, and is handled by a `low_balance` feature.

### 2.4 Target distribution
6,370 stayed (79.6%) and 1,630 churned (20.4%). The classes are
**imbalanced**, roughly 4 to 1. This drives the choice of metrics and SMOTE
later.

### 2.5 What the data says (exploration)
Churn rate by group (sample of 8,000):

| Group | Churn rate | Customers |
|-------|-----------|-----------|
| France | 16.2% | 4,011 |
| Spain | 16.7% | 1,982 |
| **Germany** | **32.4%** | 2,007 |
| Male | 16.9% | 4,339 |
| Female | 24.5% | 3,661 |
| Active member | 14.5% | 4,107 |
| Not active | 26.6% | 3,893 |
| Has credit card | 20.1% | 5,633 |
| No credit card | 21.0% | 2,367 |

| Products | Churn rate | Customers |
|----------|-----------|-----------|
| 1 | 27.5% | 4,078 |
| 2 | 7.5% | 3,651 |
| 3 | 82.3% | 220 |
| 4 | 100% | 51 |

| Age band | Churn rate | Customers |
|----------|-----------|-----------|
| 18–29 | 7.8% | 1,338 |
| 30–39 | 10.8% | 3,465 |
| 40–49 | 31.0% | 2,083 |
| **50–59** | **56.2%** | 696 |
| 60+ | 27.8% | 418 |

Correlation of each numeric column with `churn`: age **+0.285**, balance
+0.121, estimated salary +0.005, credit card −0.009, tenure −0.020, credit score
−0.024, products −0.040, active member **−0.150**.

**Key observations**
1. Churn rises sharply with age and peaks at 50–59.
2. Germany churns about twice as much as France or Spain.
3. Customers with 2 products churn least; with 1 product more; with 3–4
   products almost always churn. The 3- and 4-product groups are small
   (220 and 51 customers), so those rates are less reliable.
4. Inactive members and women churn more.
5. Credit card ownership and salary show almost no relationship with churn.
6. Relationships are **non-linear** (the product and age patterns are not
   straight lines). This suggests a tree-based model should do better than a
   linear one, which the evaluation confirms.

*These are associations in the data, not proof of cause.*

---

## 3. Data Preparation

All preparation is in `app/ml.py` and is applied **identically** when training
and when scoring new customers, so the model never sees differently prepared
data in production.

### 3.1 Cleaning (`clean_data`)
- Drop the ID column (`customer_id`).
- Fill missing numeric values with the column **median** and missing text values
  with the **most frequent value**. (The bundled data has none; this protects
  uploads of other files.)

### 3.2 Required and optional columns
Required: `credit_score, country, products_number, credit_card, active_member,
estimated_salary` and the target `churn`. Optional: `gender, age, tenure,
balance`. Features that need a missing column are skipped, so a reduced CSV
still works (tested with a 6-column file).

### 3.3 Feature engineering (`create_features`)

| Feature | Definition | Business idea |
|---------|-----------|---------------|
| `balance_salary_ratio` | balance / (salary + 1) | Financial engagement |
| `activity_score` | products × active_member | Overall engagement |
| `tenure_risk` | 1 / (tenure + 1) | Newer customers are riskier |
| `age_risk` | 1 if age < 30 or age > 60 | Demographic risk |
| `low_balance` | 1 if balance < 1,000 | Possible abandonment |
| `high_value` | 1 if balance > 100,000 and products ≥ 2 | VIP customers to protect |
| `credit_active` | credit_card × active_member | Cross product usage |

### 3.4 Encoding (`encode_features`)
- `gender` → `gender_encoded` (Male = 1, Female = 0).
- `country` → three one-hot columns (`country_France`, `country_Germany`,
  `country_Spain`). The column set is fixed, so training and serving always
  match, even if a batch file contains only one country.

Result: **19 model inputs** — 8 original numeric columns, 7 engineered features,
1 gender column and 3 country columns.

### 3.5 Train / test split and scaling (`prepare_training_data`)
- **80% train / 20% test** = **6,400 / 1,600 customers**, stratified on `churn`
  (both parts have a 20.37% churn rate), seed 42.
- A `StandardScaler` is **fitted on the training set only**, then applied to the
  test set. This avoids *data leakage* (the test set must stay unseen).

### 3.6 Class imbalance
SMOTE (synthetic minority oversampling) is applied **only to the training data
inside each cross-validation fold** during training, never to the test set.
See the SMOTE experiment in section 5.4.

---

## 4. Modeling

### 4.1 Models
| Model | Why |
|-------|-----|
| **Logistic Regression** | Simple, interpretable baseline |
| **LightGBM** (gradient-boosted trees) | Captures non-linear effects and interactions seen in section 2.5 |

### 4.2 Training procedure (`train_logistic_regression`, `train_lightgbm`)
1. Optionally oversample the training set with SMOTE.
2. **Grid search** with **5-fold stratified cross-validation**, scored by
   **ROC AUC**.
3. Keep the best parameter set and refit on the training data.

| Model | Parameter grid | Selected |
|-------|---------------|----------|
| Logistic Regression | C ∈ {0.01, 0.1, 1, 10} | C = 0.1 |
| LightGBM | n_estimators ∈ {100, 200}; learning_rate ∈ {0.05, 0.1}; max_depth ∈ {3, 5} | n_estimators = 200, learning_rate = 0.1, max_depth = 5 |

### 4.3 Model selection
The app trains the chosen models, evaluates each on the held-out test set and
uses the one with the **highest AUC** to serve predictions. It is saved to
`models/best_model.joblib` (ignored by git) so predictions still work after a
restart.

### 4.4 Training runs in the background
Training can take about a minute, so the web server runs it in a background
thread and the page polls for progress (`/api/train` and
`/api/train/results`).

---

## 5. Evaluation

All results below are on the **1,600 held-out test customers** (326 churners,
1,274 non-churners). Models were trained with SMOTE (the app default).

### 5.1 Metrics
| Metric | Logistic Regression | LightGBM |
|--------|--------------------:|---------:|
| Accuracy | 0.689 | **0.853** |
| Precision | 0.365 | **0.665** |
| Recall | **0.706** | 0.555 |
| F1 | 0.481 | **0.605** |
| ROC AUC | 0.766 | **0.850** |
| KS | 0.408 | **0.551** |

### 5.2 Confusion matrices (rows = actual, columns = predicted)
| | Logistic Regression | | LightGBM | |
|---|---:|---:|---:|---:|
| | Stay | Churn | Stay | Churn |
| **Actual Stay** | 873 | 401 | 1,183 | 91 |
| **Actual Churn** | 96 | 230 | 145 | 181 |

### 5.3 Interpretation
- **LightGBM is the best model** on AUC and KS and is selected.
- Meaning of the metrics: LightGBM ranks a random churner above a random
  non-churner about 85% of the time (AUC). When it flags a customer as a
  churner it is right 66.5% of the time (precision), and it finds 55.5% of all
  real churners (recall).
- Logistic Regression catches more churners (recall 70.6%) but with many false
  alarms (401 loyal customers flagged; precision 36.5%).
- **Trade-off for the bank:** a missed churner (false negative) costs the
  customer; a false alarm (false positive) costs a wasted retention offer. The
  default decision threshold is 0.5. The bank can pick a different threshold, or
  use the Low/Medium/High risk levels, depending on how much a retention offer
  costs versus a lost customer. **No cost figures are available in this project,
  so this trade-off is not quantified.**

### 5.4 What drives the model (LightGBM importance, share of total gain)
age 32.5%, number of products 20.5%, tenure 10.1%, tenure_risk 7.1%,
balance 6.8%, gender 4.4%, active member 3.9%, credit score 2.7%, estimated
salary 2.7%, age_risk 2.2%. This agrees with the exploration: age and product
count matter most; credit card ownership and salary barely matter.

### 5.5 Experiment: does SMOTE help?
We repeated training without SMOTE:

| | AUC | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| Logistic Regression, with SMOTE | 0.766 | 0.365 | 0.706 | 0.481 |
| Logistic Regression, no SMOTE | 0.770 | 0.626 | 0.252 | 0.359 |
| LightGBM, with SMOTE | 0.850 | 0.665 | 0.555 | 0.605 |
| LightGBM, no SMOTE | 0.859 | 0.800 | 0.491 | 0.608 |

**Finding:** SMOTE did **not** improve AUC for either model here. What it
changes is the balance of precision and recall: it raises recall (finds more
churners) and lowers precision. The F1 of LightGBM is almost identical with or
without it. The app keeps SMOTE as a checkbox (on by default) so users can
choose. Because SMOTE changes the class balance, the predicted probabilities
from a SMOTE-trained model are **not calibrated**: treat them as a ranking
score rather than the exact chance of leaving.

### 5.6 Limitations and honest caveats
- **One train/test split.** Numbers can shift by a few points with another
  random split. Cross-validation scores on the whole data set would be more
  stable.
- **One dataset, three countries.** Performance on other banks or markets is
  unknown.
- **Small groups.** Conclusions about 3- and 4-product customers (220 and 51
  customers) are weak.
- **Associations, not causes.** For example, Germany's higher churn may reflect
  something not in the data.
- **Fairness.** `gender` and `age` are model inputs and gender affects the
  predictions. Before using this on real customers, the bank should decide
  whether using these attributes is acceptable and legal in its market.
- **No business-cost evaluation** (see 5.3).

### 5.7 Review of the process
- Evaluation used data the model never saw (test set; scaler fitted on train
  only; SMOTE only on training folds).
- Automated tests (`pytest`, 11 tests) cover the ML core and the API, using
  synthetic data plus the bundled sample.
- Bugs found in the original Streamlit prototype were fixed (missing imports,
  an undefined variable in evaluation, swapped arguments in `roc_auc_score`, a
  function-name clash, and a chart rendered twice). See `docs/CHANGELOG.md`.

---

## 6. Deployment

### 6.1 What was deployed
A Flask web application (ADR
[0002](decisions/0002-use-flask-instead-of-streamlit.md)):

| Page | Purpose |
|------|---------|
| Home | Overview and how to use |
| Data | Upload a CSV or load the sample; summary, charts, correlation |
| Features | Generate features and the train/test split |
| Training | Train and compare models; ROC curves, confusion matrices |
| Prediction | Single customer (probability gauge + risk level) or batch CSV with download |

JSON API: `/api/data/*`, `/api/features`, `/api/train`, `/api/train/results`,
`/api/schema`, `/api/predict`, `/api/predict/batch`,
`/api/predict/batch/download`, `/api/status`. See `docs/architecture.md`.

### 6.2 How to run
```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py                                         # http://127.0.0.1:5000
pytest                                                # run tests
```

### 6.3 Project management and quality
- Git repository from the course starter template; branch + pull request
  workflow; CI runs the tests on every push and pull request.
- Documentation lives in `docs/`; decisions are recorded as ADRs.

### 6.4 Monitoring and maintenance plan (not implemented yet)
These are recommended next steps and are **not** part of the current app:
- Track the churn rate and score distribution over time and watch for data drift.
- Retrain periodically with recent data and compare to the current model.
- Calibrate probabilities (for example with isotonic regression) if exact
  probabilities are needed.
- Add authentication, a database and multi-user support before real use.
- Choose the decision threshold using the real cost of a retention offer.

### 6.5 Known deployment limitations
- State (loaded data, trained models) is kept in memory: one user at a time.
- Training runs inside the web process.
- Charts need internet access (Plotly.js is loaded from a CDN).

---

## Iterations (how later phases changed earlier ones)

1. **Evaluation → Data Preparation:** the first version required `age`,
   `gender`, `tenure` and `balance`. A reduced 6-column file was requested, so
   those columns became optional and features adapt automatically
   (AUC on the reduced file was 0.74 vs 0.85 with all columns, which confirms
   how informative age and balance are).
2. **Deployment → Data Understanding:** the sample dataset was bundled and
   checked (quality, class and country balance) so anyone who clones the repo
   can run the app immediately.
3. **Evaluation → Modeling:** the SMOTE experiment (5.5) showed SMOTE does not
   raise AUC, so it was kept as an optional checkbox instead of being forced.

---

_Prepared: 2026-10-21. Numbers reproduce with seed 42 on the bundled dataset._
