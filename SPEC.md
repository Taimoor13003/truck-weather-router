# Spotter AI assessment: Weather-Aware Truck Routing (React + Django)
Limit: 4 days / 16 work hours. Deliver: GitHub repo, hosted app, 5-10 min Loom (Saqib records).
Inputs: origin, destination, departure date/time, load weight.
Must: 3 route options (routing API); sample weather every 10/25/50 miles at truck ETA per checkpoint; risk per rules; recommend best route (weather risk + travel time); map showing routes, checkpoints, risk levels, ETAs, route summaries; weather heatmap along corridor with 0-48h forecast slider.
Risk table (Low/Moderate/High/Severe/No Travel):
 Wind mph: <25 / 25-34 / 35-44 / 45-54 / >=55
 Rain in/hr: <0.10 / 0.10-0.25 / 0.25-0.50 / 0.50-1.00 / >1.00
 Snow in/hr: <0.5 / 0.5-1.0 / 1.0-2.0 / 2.0-3.0 / >3.0
Load rules: >=55 mph -> No Travel any load; 45-54 mph + >30,000 lb -> No Travel; 35-44 mph + >40,000 lb -> Severe.
Recommend prefer, in order: fewest Severe miles, fewest High miles, lowest avg risk, shortest travel time.
Eval: 40% routes/weather/risk/recommendation logic; 40% UI, map, heatmap smoothness, performance; 15% code quality; 5% docs+walkthrough. Correctness and clarity over extra features.
