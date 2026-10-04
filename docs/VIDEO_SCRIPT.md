# Demo video script (2 minutes maximum)

Target length **1:50**, so there is room to breathe. About 270 spoken words.
Every number here is on the live site or in `README.md`.

## Before you record

1. Open **https://wolfhacks26-omega.vercel.app/gov** in Chrome, full screen, light mode.
2. Open **https://wolfhacks26-omega.vercel.app/m** on a phone, or in a second narrow browser window.
3. Record the screen with **Cmd + Shift + 5** (QuickTime) and the laptop microphone. One take is fine.
4. Upload to YouTube as **Unlisted**, then paste the link into Devpost's "Video demo link".

If you run out of time to record voice, record the clicks silently and read the lines over it afterwards in iMovie.

## Script

| Time | On screen | Say |
|---|---|---|
| **0:00 – 0:15** | `/gov`, statewide map, nothing selected. | "Most roads have no one watching them. North Carolina inspects its state roads, but city streets have no public ratings, and traffic cameras cover almost nothing. So repairs happen after the pothole, or after the flood." |
| **0:15 – 0:35** | Slowly move the mouse across the five number cards at the top. | "Unwatched Roads learns from the inspected roads. We score all 112,443 state road segments for three things: how fast the pavement wears, how likely it is to crack, and, in the Hurricane Helene zone, how likely it is to wash out. Six thousand seven hundred roads need fixing now." |
| **0:35 – 1:00** | Pick **Wake** in the county box. Click the first row in the work queue. Point at "Years to Poor", "Held-out", and the NCDOT record. Tick two rows and press **Add to work order**. | "This is the agency view. Pick a county and you get a ranked work list. Click a road and you see its forecast next to the state's own record. 'Held-out' means the model that scored this road never saw it, or any road within five kilometres. From here a planner builds a work order or downloads the list." |
| **1:00 – 1:25** | Click **Flood risk (Helene zone)**, then the **Storm readiness** tab. Then switch to the phone: **Model in action → Reveal what happened**. | "Before a storm, this lists the fifty roads most likely to wash out, so crews can stage nearby. We tested it on Helene. Of the fifty roads the model ranked riskiest, eighteen were actually damaged. Picking at random finds about two." |
| **1:25 – 1:42** | Back on `/gov`, click the **Model** tab. Scroll to "What we cannot claim". | "We also checked against real pothole reports. In Charlotte, the roads we rank worst draw about three times the reports of the roads we rank best. And the dashboard says what it cannot claim: one inspection per road, one storm, state roads only." |
| **1:42 – 1:50** | Zoom the map back out to the whole state. | "Next: city streets, the roads nobody inspects at all. Unwatched Roads. Fix it before it fails." |

## If you only have 60 seconds

Keep rows 1, 3 and 4. Drop the rest.

## Lines to avoid

These appear in the older pitch notes (`docs/PITCH_SCRIPT.md`) and the data does not support them, so a judge who checks could catch them:

- "92% flood hazard", "8 severe potholes", "3 extra minutes" on the Asheville route: those route cards are design placeholders, not model output.
- "18 of the top 50 in Buncombe County, before landfall": the 18 of 50 is across the whole Helene zone (32,558 roads), from a model tested on roads it had not seen. It was not a forecast made before the storm.
- "$2.4 billion", "$30 versus $5,000", "35 milliseconds": no source in the repo.
- "PMTiles": the app serves static JSON tiles, not PMTiles.
