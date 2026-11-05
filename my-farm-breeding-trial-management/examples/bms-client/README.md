<!-- Copyright 2026 Clayton Young (borealBytes / Superior Byte Works, LLC) -->
<!-- Licensed under the Apache License, Version 2.0. -->

# BMS Client (Mock)

Input:

- Synthetic trial records and a mock BMS write payload

Process:

- Simulate BMS trial read endpoint behavior
- Simulate trial write request/response output

Output:

- output/bms_trials_read.csv
- output/bms_trials_write_result.csv
- output/bms_trial_sites.csv
- output/bms_trial_site_map.png
- output/conclusion.txt

Run:

```bash
python run_bms_client.py
```

## Site map geography

`bms_trial_site_map.png` plots sites over an Esri World Imagery basemap (contextily) and
layers cached GeoAdmin context on top via `my-farm-advisor/data-pipeline/src/scripts/lib/
geoadmin_context.py`: L2 county names for every unit touching the sites, L1 state/province
labels + borders, L0 country borders. Any client example (BMS, BreedBase, IoT) can reuse
`add_admin_context(ax, sites_3857)` so a footprint map locates itself without coordinates.
