# Devpost answers: copy and paste

Every field on the Devpost form, in the order the form asks. Numbers come from `README.md` and the live dashboard.
Three things need a teammate's answer before you submit; they are marked **CHECK**.

Live site: https://wolfhacks26-omega.vercel.app

---

## Step 2: Project overview

### Project name

```
Unwatched Roads
```

### Elevator pitch (200 characters max)

```
Which North Carolina roads will fail next? We score all 112,443 state road segments for wear, cracking and flood washout, then turn it into a ranked repair list and a storm map.
```

Shorter spare, if you want one:

```
Most roads have no one watching them. We predict which North Carolina roads will crack, wear out or wash out next.
```

### Thumbnail / cover image

Upload `docs/devpost/cover.jpg` (3:2, 1500 × 1000).

---

## Step 3: Project details

### About the project (paste the whole block; it is Markdown)

```markdown
## Inspiration

Potholes and washed-out roads share a cause: water that does not drain. The places that know which roads are in trouble are the places that get inspected, and that is a small share of the map.

- **The state inspects its own roads.** NCDOT rates each stretch from 0 to 100.
- **City streets have no public ratings.**
- **Cameras see very little.** NCDOT has about 1,150 traffic cameras, mostly on interstates.

So repairs stay reactive: a road gets attention after a 311 call, or after a storm like Hurricane Helene has already taken it. For the **Center for Geospatial Analytics** track we asked a simple question. Can the roads that are inspected teach a model what age, traffic and the shape of the land do to pavement, so the roads nobody is watching get a score too?

## What it does

**Unwatched Roads** scores all **112,443 state-maintained road segments** in North Carolina (about 80,000 miles, all 100 counties). Each road gets three predictions:

- **Wear**: how many rating points it loses a year, and how many years until NCDOT would call it Poor.
- **Cracking**: the chance it has serious alligator cracking.
- **Flood failure**: for the 32,558 roads in the Hurricane Helene zone, how likely it is to wash out.

Those predictions drive three views of one web app:

- **Agency dashboard (`/gov`)**: a statewide map, a ranked work queue (6,760 roads to fix now, 11,115 within a year), work orders, CSV export, and a storm-readiness list of the 50 riskiest roads to stage crews near.
- **Phone view (`/m`)**: the same map for the field, plus a Helene backtest you can reveal yourself.
- **Executive view (`/dashboard`)**: a concept for safest-route navigation with live weather. The route comparison there is a design demo, not model output.

A second model reads a roadside camera photo and says whether the road is flooded and how deep the water is.

## How we built it

**Data, all public.** NCDOT Pavement Condition Survey, USGS 3DEP elevation (30 m), USDA NAIP 2022 aerial imagery, Hurricane Helene damage records from NCDOT, the NC Geological Survey and USGS high-water marks, Charlotte and Raleigh pothole reports, NCDOT traffic cameras, and ten coastal roadside cameras paired with water-level sensors.

**Models.** LightGBM on pavement age, traffic and terrain features (elevation, slope, relief, height above the nearest low ground). A DINOv2 vision transformer (PyTorch, timm) for the camera flood reader and for the aerial photo test.

**Honest testing.** We split the state into 5 km squares and scored every road with a model that never saw that road or any neighbour in its square. A banned-column list stops the model from peeking at the inspection rating or anything measured in the same survey.

**Web.** Vite, React and TypeScript with deck.gl on MapLibre, reading static files built from the prediction table, plus a small FastAPI service, deployed on Vercel. Behind it we built a Postgres + TimescaleDB (Tiger Data) layer for camera readings, sensor levels and pothole reports, with hypertables and continuous aggregates.

## Challenges we ran into

- **One snapshot, no history.** The state publishes one inspection per road. We had to define wear as rating lost divided by years since resurfacing.
- **Route IDs that do not match.** Two NCDOT layers encode the same route differently, so the first join matched nothing until we rebuilt the key.
- **A laptop with 18 GB of memory.** The statewide elevation grid is about 290 million cells, so we processed it in tiles.
- **Our first labels flattered us.** Pavement age was counted to the wrong year and "cracked" was too loose. Fixing both made the scores lower and the model more honest.
- **The venue network blocked the ports** for our rented GPU and for the cloud database, so the database layer was built and tested against a local TimescaleDB.
- **Aerial photos did not help.** We cut thousands of image chips and they added no reliable lift. We report that instead of hiding it.

## Accomplishments that we're proud of

- **Helene backtest.** Of the 50 roads our model ranked riskiest in the storm zone, **18 were actually damaged**. Picking at random finds about 2.
- **Checked against real potholes.** In Charlotte, the roads we rank worst draw about **three times the pothole reports per mile** of the roads we rank best, comparing roads with similar traffic.
- **Every score on the map is held-out** wherever a label exists, and each one carries a badge saying so.
- **Flood camera reader.** On a camera it had never seen, it caught **91% of flooded photos** with a typical depth miss under 10 cm.
- **Helene water depth on roads.** A depth in metres for 1,602 road segments near surveyed high-water marks, checked against 190 tape-measured depths.
- A dashboard that states its own limits: there is a "What we cannot claim" panel next to the results.

## What we learned

- The shape of the land barely changes the wear estimate. It clearly helps find cracked roads, and it helps most with flood damage.
- Random train/test splits lie for map data, because neighbouring roads look alike. Spatial blocks are slower and give numbers you can defend.
- Negative results are results. Crash counts, estimated traffic, aerial photos and a dedicated pothole model all failed to beat the simple version, and knowing that saved us from shipping noise.

## What's next for Unwatched Roads

- **Score city streets**, the roads with no public inspection at all.
- **Live camera confirmation**, so a flood alert rests on a photo as well as a prediction.
- **A budget planner** that ranks repairs by benefit per dollar, using NCDOT's own treatment and cost estimates.
- **A per-road risk feed** for navigation apps, so drivers are routed around rough or flood-prone roads.
- Load the database layer into the hosted Tiger Data service and point the dashboards at it.
```

### Built with (tags)

Type these one at a time. The draft has `opencv`: remove it, nothing in the repo uses OpenCV.

```
python, lightgbm, pytorch, scikit-learn, pandas, geopandas, rasterio, react, typescript, vite, deck.gl, maplibre, mapbox, fastapi, vercel, postgresql, timescaledb, openweathermap, ncdot, claude, codex, gemini
```

### "Try it out" links

```
https://wolfhacks26-omega.vercel.app/gov
```

```
https://wolfhacks26-omega.vercel.app/m
```

```
https://github.com/hrgang-hrushi/wolfhacks26
```

### Image gallery

Upload from `docs/devpost/` in this order (all 3:2, under 5 MB):

| File | What it shows |
|---|---|
| `01-statewide.jpg` | Agency dashboard: all of North Carolina and the ranked work queue |
| `02-wake-road.jpg` | One road in Wake County: years to Poor, wear, cracking, NCDOT record |
| `03-storm.jpg` | Storm readiness: the 50 riskiest roads in the Helene zone |
| `04-model.jpg` | Model transparency: the "Does it work?" table inside the app |
| `05-dark-charlotte.jpg` | Dark mode, cracking risk in Mecklenburg County |
| `06-phone.jpg` | Phone view: condition map, flood map, Helene backtest |

### Video demo link

Record with `docs/VIDEO_SCRIPT.md`, upload to YouTube as **Unlisted**, paste the link.

---

## Step 4: Additional info

### Sponsor / special prizes

The draft has three ticked. Check each one against what we actually built:

- **[MLH] Best Use of Tiger Data**: keep. `web/tiger/` and `web/service/` are a real Postgres + TimescaleDB layer (hypertables, continuous aggregates, compression) with 123 passing tests. It ran against a local TimescaleDB, not the hosted Tiger Data service, because the venue network blocked the port. Say so if a judge asks.
- **[MLH] Best Use of Gemini API**: **CHECK.** Nothing in the repo calls the Gemini API, and the form asks for a Gemini Project Number. Keep it only if a teammate has a Gemini feature and the project number. Otherwise untick it.
- **[MLH] Best Domain Name from GoDaddy Registry**: **CHECK.** The site is on `wolfhacks26-omega.vercel.app`. Keep it only if someone registered a domain through the MLH GoDaddy offer.

### What track are you competing in?

```
Center for Geospatial Analytics Track
```

### GitHub repository URL

```
https://github.com/hrgang-hrushi/wolfhacks26
```

### Universities or schools

```
North Carolina State University & Wake Tech
```

### Feedback about any technology you used

```
Tiger Data (Postgres + TimescaleDB): hypertables and continuous aggregates fit our time-stamped camera, sensor and pothole data well, and compression was one setting. The one snag was the venue Wi-Fi blocking the database port, so we developed against a local TimescaleDB. A browser-console import path or an HTTPS endpoint would have saved us.

Vercel: push-to-deploy for a Vite frontend plus a Python service worked well. One surprise: the production build handled per-page CSS differently from the dev server, so test with a real build.

NCDOT open data (ArcGIS): no key needed and very broad. The route ID is encoded differently between layers, which cost us a few hours.

Claude Code and OpenAI Codex: we used one to write and the other to review. Having a second model audit the plan and the results caught label mistakes we would have shipped.

deck.gl + MapLibre: drew 112,443 road segments smoothly in the browser once the data was split into tiles.
```

### Which AI tools did you use this weekend?

```
OpenAI, Anthropic, Gemini
```

### Did you implement a generative AI model or API in your hack this weekend?

**CHECK:** the text below does not say how Gemini was used, because nothing in the repo shows it. Whoever used Gemini should add one sentence at the end.

```
Our prediction models are not generative. They are gradient-boosted trees (LightGBM) and a DINOv2 vision transformer that we fine-tuned to read flood depth from camera photos.

We used generative AI in two places. First, Claude acted as a vision grader: it looked at 141 clear NCDOT traffic-camera stills and labelled visible pavement damage, as an independent check on our predictions (two grading passes agreed on 35 of 40 stills). Second, Claude Code and OpenAI Codex were our coding assistants, and we had each one review the other's plans and results before we trusted a number.
```

### Gemini Project Number

**CHECK.** Only needed for the Gemini prize. Whoever owns the Gemini API key gets it from Google AI Studio → Get API key → Project number. Leave blank if we are not entering that prize.
