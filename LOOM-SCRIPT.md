# Loom walkthrough script (aim for 6 to 8 minutes)

Record screen + voice. Speak slowly; simple English is fine. Say only what is true.

## 1. Intro (20 s)
"Hi, I'm Muhammad Saqib. This is my solution to the Spotter full stack assessment: a weather-aware truck routing app built with React and Django."

## 2. Demo (2 min), open the hosted app
- Enter Dallas, TX to Chicago, IL, load 45,000 lb, leave departure as is, 25-mile checkpoints. Click Plan.
- "It returns three real route options from OSRM. Each card shows distance, travel time, arrival, a bar showing risk along the route, and miles at High and Severe."
- Click a route: "Checkpoints appear every 25 miles. Click one: you see the ETA, wind, rain, snow and the risk level, with the reasons."
- Show the table: "The weather used is the forecast for the time the truck will actually be at that checkpoint, not now."
- Plan Los Angeles to Chicago: "On long trips the driver must stop: a 30-minute break after 8 hours and a 10-hour rest after 11 hours of driving. B and R markers show where, and every later ETA moves back, so the weather is checked for the right time."
- Then try Amarillo, TX to Denver, CO: "Here the recommendation changes, and the text explains the trade-off between time and risk."
- Drag the slider: "The heatmap shows the forecast risk along all routes from 0 to 48 hours after departure. It recolours instantly because the backend already computed every hour."

## 3. How the backend works (2 min), show backend/routing/services
- osrm.py `parse_route`: "OSRM gives a travel time for every small road segment. I cap each at 65 mph for a truck."
- hos.py: "Hours-of-Service rules turn driving time into real clock time."
- planner.py: "Checkpoints are placed along the route geometry and get their ETA from those two steps."
- weather.py: "One batched Open-Meteo request for many locations, in parallel, cached for 30 minutes."
- risk.py: "The thresholds from the brief, plus the load-weight rules. This is the core logic, so it has unit tests."
- planner.py `_rank_key`: "Ranking: avoid No Travel, then fewest Severe miles, then High miles, then average risk, then time."
- osrm.py: "If OSRM gives fewer than three distinct routes, I request more with via-points and filter duplicates and big detours."

## 4. Frontend (1 min)
- HeatLayer.js: "Colour shows risk level, not density, so overlapping points do not turn red by accident."
- MapView.jsx: "Routes redraw only when the plan or selection changes; the slider only updates the heat layer."

## 5. Trade-offs and what I would do next (1 min)
- "The free router only has a car road network, so low bridges and truck-restricted roads are not checked. I slow every segment to 65 mph and add the driver's required breaks and 10-hour rests, but a commercial truck router would be the next step; only osrm.py would change."
- "Free public services have rate limits; in production I would use a paid routing and weather provider and cache by corridor."
- "Gusts, visibility and ice are not in the brief, so I left them out."

## 6. Close (10 s)
"Code and hosted link are in the submission. Thank you."
