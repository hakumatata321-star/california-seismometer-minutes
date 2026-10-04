# California Seismometer Minutes with Network Catalogue Earthquakes

## Overview

This dataset pairs real one-minute seismometer recordings with the earthquakes that the regional seismic networks catalogued in them. Each example is one minute of vertical ground velocity from a cluster of up to 12 stations of one network, with the stations' positions relative to the example's centre. Each example comes with the network's catalogue entries for that minute and area. The southern examples come from the Southern California Seismic Network, which is built mostly from broadband seismometers. The northern examples come from the Northern California Seismic Network, which relies mostly on short-period seismometers. Nothing in the dataset is simulated or generated: every sample and every catalogue entry comes from the networks' public archives.

## Source

- Continuous waveforms: SCEDC (`s3://scedc-pds/continuous_waveforms/`, channel HHZ, network CI) and NCEDC (`s3://ncedc-pds/continuous_waveforms/NC/`, channel EHZ, network NC), 2023, 100 samples per second.
- Station positions and sensitivities: the SCEDC and NCEDC FDSN station web services.
- Catalogues: the SCEDC catalogue (`earthquake_catalogs/SCEC_DC/2023.catalog`) and the NCEDC catalogue (`earthquake_catalogs/NCEDC/2023.ehpcsv`).

## How the examples were built

1. For each day, catalogue earthquakes were used as anchors. Each example centre lies at a random point up to 30 km from an anchor epicentre. For quake examples, the anchor is an earthquake of that day and the minute starts 2 to 50 seconds before its origin time. For quiet examples, the anchor is an earthquake from another day and the minute starts at a random time of the day.
2. The 12 nearest stations within 75 km of the centre were taken (at least 5). An example was skipped when it would share a station with an already accepted example of the same day over overlapping minutes.
3. Each trace was demeaned, tapered and band-passed from 1 to 20 Hz (4-pole, zero phase) on a 10-second margin around the minute, decimated to 50 samples per second, and divided by the channel's overall sensitivity to give ground velocity in nanometres per second. Gaps inside a day file were filled with zeros. Traces that were missing, too short or entirely zero were dropped, and their slot was marked absent.
4. Station positions were converted to kilometres east and north of the centre with a local flat-Earth projection.
5. Catalogue earthquakes (event type `eq`) with an origin inside the minute and an epicentre within 60 km of the centre are the scored entries. Other catalogue entries nearby in time and space are kept as neutral entries: earthquakes just outside the minute or the circle, and quarry blasts and explosions.
6. Every example received a keyed identifier that reveals nothing about its date, time or position.

The builder script `build_examples.py` reproduces steps 1 to 5 from the public archives.

## Contents

- `examples.csv`: `example_id` and `split` (train for southern examples, test for northern examples).
- `southern_waveforms.npz` and `northern_waveforms.npz`: `example_id`, `velocity` (N, 12, 3000) float32 in nm/s, and `present` (N, 12) uint8, 1 where a slot holds a trace.
- `stations.csv`: one row per example and present slot, with `example_id`, `slot`, `east_km`, `north_km` and `elevation_m`.
- `catalogue.csv`: one row per catalogue entry, with `example_id`, `origin_s` (seconds from the start of the minute), `east_km`, `north_km`, `magnitude` (the network's preferred magnitude) and `scored` (1 for scored entries, 0 for neutral ones).
- `build_examples.py`: the builder.
- `LICENSE`: terms and required citations.

## Intended Use

The dataset is meant for research and benchmarking on detecting and locating small earthquakes from sparse seismometer clusters, and on transferring such methods from one seismic network to another with different instruments, noise and geology. It also suits teaching seismology and event-detection evaluation. It is not intended for earthquake early warning or any safety decision.

## Known Limitations

- Only the vertical component is included, sampled at 50 Hz and band-limited to 1 to 20 Hz. The two networks use different sensors, and dividing by a single sensitivity value does not fully correct the short-period sensors' response below a few hertz.
- The labels are the networks' own catalogues. They miss some of the smallest events, their locations carry errors of up to a few kilometres for small events, and the two networks use different magnitude types (local magnitude in the south, mostly duration magnitude in the north).
- Origin times and epicentres come from each network's own velocity model and location procedure, which differ between the two networks.
- Depth is not part of the labels, and the station positions use a flat-Earth approximation that is accurate to well under 1 km at these distances.
- Examples were chosen around catalogued earthquakes, so they contain far more earthquakes than random minutes would. The northern examples include many events from The Geysers geothermal field.
- Coverage is limited to 2023, to the stations active on each day, and to the days listed in the builder settings.

## Licence

The data are used under the SCEDC and NCEDC licences (non-exclusive, royalty free, worldwide right to use, reproduce and publicly display), with the citations given in `LICENSE`. The compilation is released under CC BY 4.0.
