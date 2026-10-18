# Airport Investment Agent

A chat assistant that helps an airport-modernization investor answer: **where in the U.S. would a renovation add the most flight and passenger capacity, and so pay off best?**

## What it does

Ask in plain English, for example *"Which New England airports are strong candidates for expansion?"* For each airport it gives:

- **An opportunity score (0–100):** how many passengers, how fast traffic is growing, and how full the planes already are.
- **What limits growth, and so what to invest in:**
  - **Terminal**: demand is pressing on the building → terminal expansion pays.
  - **Airfield**: runways or airspace are the bottleneck → airfield projects pay; a bigger terminal alone won't add flights.
  - **Regulatory**: a legal cap binds → capital can't add capacity until the rules change.
  - **None evident**: demand isn't pressing yet → wait.
- **Where every number came from**, and what the data can't tell you.

## Why you can trust the numbers

The AI (Claude) never calculates. Python computes every number from public U.S. government data, and Claude only explains it. After each answer, a check confirms that every number came from the data.

## For reviewers (about 5 minutes)

Requires Python 3.11 or newer.

**1. Install**
```bash
git clone https://github.com/nimrodpardess7-dotcom/airport-investment-agent.git
cd airport-investment-agent
python -m venv .venv
.venv\Scripts\activate          # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

**2. Run the chat**
```bash
streamlit run app.py            # opens http://localhost:8501
```
The agent is live, so it needs an Anthropic API key. **Paste yours in the sidebar.** It's used only for that browser session and never saved. (Or put it in a `.env` file: copy `.env.example` and fill in `ANTHROPIC_API_KEY`.) Each answer costs about $0.05.

Then click one of the four example questions, or ask your own. Follow-ups work ("and Hartford?", "what if growth matters twice as much?").

**3. No key? The scoring still runs**
```bash
python scripts/four_questions.py   # the four questions, computed in Python, no AI
python -m pytest                   # 92 tests
```

The first run downloads public data (about 1–2 minutes); after that it's cached.

## What to read

1. **[docs/DESIGN.md](docs/DESIGN.md)**: scoring, tradeoffs, where AI is used, limits (the design document).
2. **[docs/eval_outputs/](docs/eval_outputs/)**: the agent's real answers to the four brief questions.
3. **[docs/eval_results.md](docs/eval_results.md)**: end-to-end eval, 8 cases graded in code.
4. [config.yaml](config.yaml) and [kb/](kb/): every weight, threshold, fact and assumption, editable.

History (how it was built, not the current design): [docs/history/](docs/history/) holds the original plan and the data-source checks. `CLAUDE.md` holds the instructions for the AI coding assistant used during the build.
