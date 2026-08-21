# SETUP.md -- Light Posting Alert Agent

**Repo:** `light-posting-alert`
**Pair:** Luca + Hudson
**Deadline:** Friday EOD

Read this first. It covers repo setup, the Step 0 handshake, branch workflow, and the merge sequence. The per-person build plans (`hudson-plan_revised.md`, `luca-plan_revised.md`) cover what to actually build.

---

## What we are building

A script that polls the Light demo environment via API for invoices sitting in draft or awaiting posting, and sends a Slack message to the assignment channel summarizing what needs attention: who, what, how much, how old. It should read like something a finance person actually wants. Running it on a schedule is a stretch goal, not a requirement.

**Sprint rules:**
- Claude Code for everything, that is the point
- Keep a build log: what you prompted, what broke, how you fixed it
- Friday EOD: 10 to 15 min demo (screen recording is fine) plus post the build log

---

## Part 1 -- Repo setup (do this once, together, 10 min)

Everything happens in the `light-posting-alert` folder. One folder, one repo, no duplicates.

### 1a. Create the scaffold

```bash
cd light-posting-alert

mkdir -p src tests data output
touch src/__init__.py tests/__init__.py

# Claude Code cannot import anything without these __init__.py files.
# This is the most common first-hour time sink. Do it now.
```

Target structure after setup:

```
light-posting-alert/
  src/
    __init__.py
    models.py            <- Step 0, shared
    light_client.py      <- Step 0, shared
  tests/
    __init__.py
  data/                  <- Luca fills in Phase 1
  output/                <- FileSink writes here
  .gitignore
  requirements.txt
  build-log.md
```

### 1b. Create `.gitignore` before anything else

```
.env
__pycache__/
*.pyc
.venv/
venv/
output/
.pytest_cache/
```

`.env` must be in here before any credentials are added anywhere. This is the single most common way API keys leak.

### 1c. Create `requirements.txt`

```
pydantic>=2.0
httpx
python-dotenv
schedule
pytest
```

### 1d. Set up the virtual environment

Each person, on their own machine:

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 1e. Create an empty build log

```bash
touch build-log.md
```

Add a header:

```markdown
# Build Log -- Light Posting Alert

Format per entry: what we prompted Claude Code with, what came back,
what broke, how we fixed it. Do not clean up the "what broke" entries,
those are the point.

## Setup
- [timestamp] Repo scaffolded, venv created, deps installed.
```

### 1f. First commit

```bash
git add .
git commit -m "Scaffold: project structure, gitignore, requirements"
```

---

## Part 2 -- Step 0 handshake (15 min, non-negotiable, do this together)

Before either person writes any other code, sit together and commit these two files to `main`. Everything branches off them.

**Files to create:** `src/models.py` and `src/light_client.py`. The exact contents are in both build plans, they are identical in each, copy from either.

**Two decisions to make in this same 15 minutes:**

1. **What does "how old" mean?** Days stuck in the current status (`updatedAt`), or days past due date (`dueDate`)? The model carries both. Default to status age since that is what this agent is chasing, but write the decision down, a finance person may read "how old" the other way. Be ready to mention it in the demo.

2. **Is `config.AGING_THRESHOLDS` and `config.TIMEZONE` actually wired in, or are we hardcoding?** Either is acceptable for a one-day sprint. What is not acceptable is config values that exist but nothing reads. Pick one, note it in `build-log.md`.

**Then commit:**

```bash
git add src/models.py src/light_client.py
git commit -m "Step 0: shared models and client interface"
git push -u origin main     # if using a remote
```

Only after this commit do you split.

---

## Part 3 -- Branch workflow

```bash
# Luca
git checkout main
git checkout -b luca/data-logic-formatting

# Hudson
git checkout main
git checkout -b hudson/infra-client-cli
```

### The config stub problem

Luca's `aging.py` imports `config.AGING_THRESHOLDS`, but `src/config.py` is Hudson's file and does not exist on her branch. She needs a stub so her tests can run independently:

```python
# src/config.py  (STUB on Luca's branch, Hudson's real version wins at merge)
AGING_THRESHOLDS = [7, 14, 30]
TIMEZONE = "UTC"
```

At merge, Hudson's full `config.py` replaces this. Flag it in the merge checklist below so nobody accidentally keeps the stub.

### The reverse problem

Hudson's `main.py` imports Luca's `mock_client`, `grouping`, and `formatter`, which do not exist on his branch. This is expected. He can either write throwaway stubs or simply accept that `main.py` will not run until merge, and test his own files (`config.py`, `sinks.py`, `live_client.py`) in isolation.

### File ownership, no overlap by design

| Luca | Hudson | Shared |
|---|---|---|
| `src/mock_client.py` | `src/config.py` | `src/models.py` |
| `src/aging.py` | `src/sinks.py` | `src/light_client.py` |
| `src/grouping.py` | `src/live_client.py` | `build-log.md` |
| `src/formatter.py` | `src/main.py` | |
| `data/*.json` | `requirements.txt` | |
| `tests/*.py` | `.env.example`, `README.md` | |

The only file both people touch is `build-log.md`. That is the only place a merge conflict should ever appear.

---

## Part 4 -- Prompting Claude Code

Feed the plan to Claude Code **one phase at a time**, not all at once. Scoped prompts produce better output and let you verify each phase before moving on.

**Luca, roughly:**

```
Prompt 1: "Here's my plan [attach luca-plan_revised.md]. The scaffold is set up
with models.py, light_client.py, and a config stub. Do Phase 1 only: mock data
files in data/ and MockLightClient in src/mock_client.py. Follow the spec exactly
for the 10 invoices."

Prompt 2: "Now Phase 2. Tests first in tests/test_aging.py and
tests/test_grouping.py, including the naive datetime test. Then implement
src/aging.py and src/grouping.py. Run pytest and fix until green."

Prompt 3: "Now Phase 3. Implement src/formatter.py with format_blocks and
format_plain, plus tests/test_formatter.py. Use Slack Block Kit format
(header, section with mrkdwn, divider, button accessory). The plain text
output must read like something a finance person wants, not raw enum values."
```

**Hudson, roughly:**

```
Prompt 1: "Here's my plan [attach hudson-plan_revised.md]. Do Phase 4 and 5:
src/config.py, .env.example, and src/sinks.py with the three sinks."

Prompt 2: "Now Phase 6. Write src/live_client.py against the Light API docs.
Mark every field-name guess with a NOTE comment, we verify against the real
API next."

Prompt 3: "Now Phase 6b. I have demo credentials. Run against the real API,
compare the actual response shape to our guesses, and fix the code to match."

Prompt 4: "Now Phase 7. src/main.py with the CLI, error handling around
run_once, and the schedule flag."
```

**Log every prompt as you go.** Petr asked for it explicitly and reconstructing it at 5pm Friday is miserable.

---

## Part 5 -- Merge

When both branches are done:

```bash
git checkout main
git merge luca/data-logic-formatting
git merge hudson/infra-client-cli
```

Expect exactly one conflict: `build-log.md`. Resolve by keeping both sets of entries in chronological order.

### Merge checklist

- [ ] Luca's `config.py` **stub is gone**, Hudson's real version is in place
- [ ] `build-log.md` conflict resolved, both people's entries preserved
- [ ] `.env` is NOT committed (`git ls-files | grep .env` should show only `.env.example`)
- [ ] Function signatures match: `format_blocks(summary) -> list[dict]` and `format_plain(summary) -> str`
- [ ] If they do not match, agree on a fix in 5 minutes, do not silently adapt around each other

---

## Part 6 -- Validation gates

Run all four in order. Do not skip gate 2, it is the one that actually proves the assignment.

```bash
# Gate 1: tests pass
pytest tests/

# Gate 2: mock mode runs clean, no credentials needed
python -m src.main --mock --output console

# Gate 3: live mode runs clean against the real demo environment
python -m src.main --live --output console

# Gate 4: message actually lands in the Slack channel
python -m src.main --live --output slack
```

Gate 3 is where field-name guesses in `live_client.py` die. If the real API returns a different response envelope or pagination style than assumed, fix it here and record what was wrong in `build-log.md`. That entry is one of the most valuable things in the log.

If the demo environment is unreachable, fall back to mock mode for the demo, but record it as a documented blocker, not a silent omission.

---

## Part 7 -- Demo deliverables

**Recording, 10 to 15 min, cover:**
1. What the agent does and why (30 sec)
2. Live run against the demo env, show the Slack message landing
3. Walk through the Slack output: who, what, how much, how old, explain why it is formatted for a finance reader
4. Mention the "how old" decision from Step 0 (status age vs due date) and why you chose what you chose
5. One or two things that broke and how you fixed them, pulled straight from the build log
6. If scheduling got done, show `--schedule`. If not, say so, it is a stretch goal

**Post to the channel:**
- The recording
- `build-log.md`
- Repo link if it is shared

---

## Quick reference

```bash
# Activate env
source .venv/bin/activate

# Run tests
pytest tests/

# Mock run
python -m src.main --mock --output console

# Live run
python -m src.main --live --output console

# Send to Slack
python -m src.main --live --output slack

# Scheduled (stretch)
python -m src.main --live --output slack --schedule
```
