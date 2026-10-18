# KelpObserve Sesimbra 2026: tidy tables

`make_tidy_tables.py` builds the six tidy tables of the dataset *KelpObserve Sesimbra 2026: diver
quadrat surveys of the kelp* Saccorhiza polyschides *and water-column sonde profiles, Arrábida
coast, Portugal* (version 1.0.0, Zenodo,
[doi:10.5281/zenodo.23282075](https://doi.org/10.5281/zenodo.23282075)) from the five files that
CCMAR delivered.

```bash
python make_tidy_tables.py --raw-dir raw --out-dir tidy
```

The repository holds the script, `requirements.txt`, `LICENSE` (Apache 2.0), `CITATION.cff` and
`.python-version` (3.12). The Zenodo record links here for the script, and its
`release_provenance.json` records the SHA-256 of the script version that built release 1.0.0.
The transect and mapping videos are in a companion record,
[doi:10.5281/zenodo.23350632](https://doi.org/10.5281/zenodo.23350632).

Pine View Software AS (Pineview, Norway) wrote the script for KelpObserve, an AQUASERV
Transnational Access project (PID 42082) hosted by CCMAR (Centro de Ciências do Mar do Algarve,
Universidade do Algarve, Faro, Portugal).

## Inputs

Download the five delivered files from the Zenodo record into one folder, keeping the names they
carry there. The record holds release copies of the CCMAR delivery, with the scientific content
unchanged.

| File | Contents |
| --- | --- |
| `raw_ccmar_kelp_quadrats_2026.xlsx` | kelp workbook |
| `raw_ccmar_sonde_casts_2026.xlsx` | sonde workbook |
| `raw_ccmar_quadrat_positions_2026.gpkg` | quadrat positions |
| `raw_ccmar_quadrat_positions_july_dive_log.gpkg` | timed July dive log |
| `raw_ccmar_dive_tracks_2026.gpkg` | dive tracks |

## Requirements

The script needs Python 3.10 or later with pandas, openpyxl, geopandas (pyogrio) and pyproj.
`requirements.txt` pins the versions used to build release 1.0.0 under Python 3.12.0: pandas
3.0.5, numpy 2.5.1, openpyxl 3.1.5, geopandas 1.1.4, pyogrio 0.13.0, shapely 2.1.2 and pyproj
3.7.2.

## Run

With the five files in `raw/`:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python make_tidy_tables.py --raw-dir raw --out-dir tidy
```

The six tidy files are written to `tidy/`.

## Outputs

| File | One record per | Records |
| --- | --- | --- |
| `kelp_quadrats.csv` | surveyed quadrat | 90 rows |
| `kelp_quadrats.geojson` | surveyed quadrat: the rows of `kelp_quadrats.csv` as points | 90 points |
| `kelp_individuals.csv` | measured kelp individual | 242 rows |
| `sonde_casts.csv` | sonde cast | 7 rows |
| `sonde_profiles.csv` | sonde sample | 1,390 rows |
| `dive_tracks.geojson` | campaign: the GPS track of the divers' surface float | 3 tracks |

The record's `README.md` and `data_dictionary.csv` document every column of these files and every
known issue of the data.

### What the script does

- Renames columns.
- Groups the rows of the kelp workbook into quadrats by date, depth, transect and quadrat number.
  Each measured individual becomes one row of `kelp_individuals.csv`; the per-quadrat cover,
  erosion and epibiont values go to `kelp_quadrats.csv`.
- Joins each quadrat to the position with the same campaign, stratum, transect and quadrat number.
  The kelp workbook and the position file label the strata with different depths, so the join key
  is the stratum.
- Adds the date, time and tape mark of each July quadrat from the timed dive log.
- Swaps the sonde dates back from their day-first storage, and marks the profile leg of each cast:
  the samples between its shallowest and deepest reading.
- Rounds the dive-track coordinates to seven decimals and drops their Z values.
- Adds `survey_date` and `survey_date_evidence` from the campaign chronology, which is encoded
  explicitly in the function `survey_date()`, and retains the source date fields.

Nothing is modelled, interpolated, offset, filtered or binned, and no observation is removed.

## Verify

The SHA-256 of this version of `make_tidy_tables.py` is
`7795d780d768da55f956509a1519bbc4510c2b12ee8249f6b9bc84509a35d4fd`. Compare it with the value in
the record's `release_provenance.json`:

```bash
shasum -a 256 make_tidy_tables.py
```

Run on the five files of release 1.0.0, the script reproduces the six tidy files byte for byte.
Their SHA-256 values are also listed in the record's `checksums.sha256`. To check the rebuilt
files:

```bash
cd tidy
shasum -a 256 -c <<'EOF'
f79ad2d68b5a01d84c507745978b9f0c2d5f2b259e6ea215f5f3371e963f9e56  kelp_quadrats.csv
80d51420b50872fcdb06f8a2377ffe4dae7712826e3e4666e236eb691321c80e  kelp_quadrats.geojson
266629ea8fd8f7070b5aa236030ef679d912bf1eae9f44f76845f5328d4f09b8  kelp_individuals.csv
a6499e905dc1e4cf8e7a4360ca2005e5ba86bd8c6338987f0e2e24e461f227a0  sonde_casts.csv
810753bb36816d2a156810d3292cf8876645d93db2ed6ce4cae69d6018eb261a  sonde_profiles.csv
39545eb03d45f11c3dc4e84c3448d69a7e7ada0c1e2aa73d74b48108c903e50d  dive_tracks.geojson
EOF
```

Each matching file prints `OK`. On Linux, `sha256sum -c` reads the same input.

## Not in this repository

- The data files. The five inputs and the six tidy files are in the Zenodo record.
- The packing of the quadrat photographs, the bathymetric position check (`position_qc.csv`), the
  overview map and the generation of the record's documentation. Other Pineview tooling produced
  them; none of them is needed to rebuild the tidy tables.

## Licence and citation

The code is released under the Apache License 2.0 (see `LICENSE`).
The data are licensed CC BY 4.0 under the Zenodo record.

Cite the data as:

> Rusu, A., Botezat, O., Paulo, D., Encarnação, J., Rosado, G. (2026). KelpObserve Sesimbra 2026:
> diver quadrat surveys of the kelp Saccorhiza polyschides and water-column sonde profiles,
> Arrábida coast, Portugal (Version 1.0.0) [Data set]. Zenodo.
> https://doi.org/10.5281/zenodo.23282075

`CITATION.cff` gives the citation for the software.

## Credits

The CCMAR Scientific Dive Centre (Diogo Paulo, João Encarnação, Guilherme Rosado) made the field
surveys. The dataset's creators are Andrei Rusu and Oana Botezat (Pine View Software AS) and Diogo
Paulo, João Encarnação and Guilherme Rosado (CCMAR). Pine View Software AS wrote the script.

Contact: Andrei Rusu, Pine View Software AS.

## Funding

The project leading to these results has received funding from the European Union's Horizon
Europe research and innovation programme under grant agreement No 101131121 (AQUASERV), through
Transnational Access project PID 42082 (KelpObserve) hosted by CCMAR. This study received support
from the Portuguese node of EMBRC-ERIC, specifically EMBRC.PT ALG-01-0145-FEDER-022121. This output
reflects only the authors' view and the European Union cannot be held responsible for any use that
may be made of the information contained therein.

AQUASERV Transnational Access supported access to the coastal study site and field services
provided by CCMAR, together with travel and accommodation for Pineview staff. Subsequent
KelpObserve data processing and analysis, software development, and preparation of the research
outputs were carried out by Pineview through its own in-kind contribution.
