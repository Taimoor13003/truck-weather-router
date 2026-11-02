# Loom walkthrough script (aim for 7 to 9 minutes)

Record screen + voice. Speak slowly; simple English is fine. Say only what is true.
Before recording: open the hosted app once (the free server sleeps and the first load is slow), and open the repo in VS Code.

## 1. Intro (20 s)
"Hi, I'm Muhammad Saqib. This is my solution to the Spotter full stack assessment: a weather-aware truck routing app built with React and Django."

## 2. Demo (3 min), in the hosted app
- Enter Minneapolis, MN to Fargo, ND, load 45,000 lb, 25-mile checkpoints. Click Plan.
- "It returns three real route options. Each card shows distance, driving time, arrival, a bar of risk along the route, and miles at High and Severe. The recommended route has a one-line reason."
- Point at the grey line above the cards: "Times are in the origin's own time zone, here CST, and it says which weather service was used."
- Click a checkpoint on the map: "Every 25 miles: the ETA, wind, rain, snow, the risk level and why."
- Scroll the table: "The weather used is the forecast for the time the truck will actually be at that checkpoint, not the weather now."
- Change load weight to 35,000 or 25,000 and plan again if there is wind on the route: "The load rules change the result: in 45 to 54 mph wind, over 30,000 lb is No Travel."
- Plan Los Angeles, CA to Chicago, IL: "On long trips the driver must stop by law: a 30-minute break after 8 hours and a 10-hour rest after 11 hours of driving. B and R markers show where, and every later ETA moves back, so the weather is checked for the right time."
- Press play on the heatmap: "This is the forecast risk along all three routes from 0 to 48 hours after departure. It moves in 15-minute steps and blends colours, and needs no extra requests because the backend already computed every hour."

## 3. Backend (2.5 min), show backend/routing/services
- risk.py: "The thresholds and load rules from the brief, as small pure functions. Each one has a unit test."
- osrm.py `parse_route`: "OSRM gives a travel time for every small road segment. I cap each at 65 mph for a truck."
- hos.py: "Hours of Service turns driving time into real clock time."
- planner.py `build_checkpoints`: "Checkpoints along the route geometry get their ETA from those two steps."
- weather.py: "Open-Meteo in batches, in parallel, cached. If it is down, MET Norway fills the gap, so the app keeps working."
- planner.py `_rank_key`: "Ranking: avoid No Travel, then fewest Severe miles, then High miles, then average risk, then time."
- osrm.py `fetch_routes`: "If OSRM gives fewer than three distinct routes, I request more through side via-points and drop duplicates and big detours."
- tests.py `PlanPipelineTests`: "The whole pipeline is tested with fake services: a gale on one road must send a heavy truck the other way."

## 4. Frontend (1 min)
- HeatLayer.js: "A small custom canvas layer. Colour is risk level, not point density, so overlapping points do not turn red by accident."
- MapView.jsx: "Routes redraw only when the plan or selection changes; the slider only recolours the heat layer, so it stays smooth."

## 5. Trade-offs and next steps (1 min)
- "The free router only has a car road network, so low bridges and truck-restricted roads are not checked. A commercial truck router would be the next step; only osrm.py would change."
- "Free public services have rate limits. In production I would use paid providers and cache forecasts by corridor."
- "Gusts, visibility and ice are not in the brief, so I left them out on purpose: the brief asks for correctness and clarity over extra features."

## 6. Close (10 s)
"The code, README and hosted link are in the submission. Thank you."
