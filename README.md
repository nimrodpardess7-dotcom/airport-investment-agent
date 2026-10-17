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
