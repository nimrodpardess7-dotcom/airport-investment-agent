# Airport Investment Agent

A chat assistant for one question: **which U.S. airports are worth investing in a new terminal, and what could block it?**

## What it does

Ask in plain English, for example *"Which New England airports are the best candidates?"* It answers with:

- **A score (0–100)** for each airport: how many passengers, how fast traffic is growing, and how full the planes are.
- **What blocks growth:** a legal cap, the runways, or the terminal itself. Only the last one is fixed by building a terminal.
- **Where every number came from**, and what the data can't tell you.

## Why you can trust the numbers

The AI (Claude) never calculates. Python computes every number from public U.S. government data, and Claude only explains it. After each answer, a check confirms every number came from the data.

## Try it

```bash
python -m venv .venv
.venv/Scripts/activate          # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add your ANTHROPIC_API_KEY
streamlit run app.py
```

Click one of the example questions in the sidebar.

## More

- How the score works, the tradeoffs and the limits: [docs/DESIGN.md](docs/DESIGN.md)
- Tests: `python -m pytest`
