# Project notes

Melon-only chart bot for the DC Circle Chart minor gallery. It fetches Melon app endpoints, computes charts itself, renders PNGs and posts them to the gallery tab "차트".

## What gets posted (config.actions.toml `own_charts`)
- `own_top100`: TOP100 table, hourly, about :04 (Melon applies the new hour late).
- `own_users`: listener-count trend of the top 3, hourly, about :05-:08 (waits until Melon fills the counts, gives up after :19).
- `own_predict`: next-hour TOP100 prediction at :50 only (Melon's official prediction).
- 5-minute charts (`own_hot5`, `own_melon5`) exist but are switched off. Never post the rank graph.

## Workflows
- `recorder.yml` (mode=loop): saves raw Melon responses to branch `livedata` every minute. Scheduled runs are unreliable, so it is re-dispatched by hand (28 min per run).
- `upload.yml`: `python run.py own`; inputs `dry` and `minutes`. Cancel and re-dispatch to deploy a change (state is restored from the Actions cache `upload-state-*`).
- `lag.yml`, `peak.yml`, `probe.yml`: measurement jobs that write to branches `lag`, `peak`, `probe`. Do not overwrite these branches.
- Melon endpoints answer only from the runner, not from sandboxes.

## Data rules
- Data comes from our own fetching and computing. Gaisum is used only as a one-time seed: earlier hours in the listener table (`probe` branch) and all-time peak listeners (`peak` branch).
- Peak listeners per song = max(known counts, seeded all-time peak).
- Measured Melon lag: 5-minute values +1-12 s after the tick, prediction +1-5 s, hourly list +3-4 min after :00, hourly listener counts about +5 min.

## Posting
- Posting takes 30-40 s per post (browser automation in `chartbot/dcinside.py`); 2 parallel workers with a priority queue (predict first). Stops after 3 consecutive failures.
- Gallery id, minor flag, nickname and password come from repo Variables and Secrets (`DC_*`); the tab name defaults to "차트" (`DC_HEADTEXT`).
- `backup-main` branch keeps the old commit history.
