# Changelog

The software builds the dataset on Zenodo ([doi:10.5281/zenodo.23282075](https://doi.org/10.5281/zenodo.23282075)). Version 1.1.0 builds release 1.0.0 of the dataset as published. Version 1.0.0 built an earlier state of that record, before CCMAR curated the sonde workbook for release.

## 1.1.0

- `make_tidy_tables`: reads the report sheet of the sonde workbook that CCMAR curated for release. `sonde_profiles.csv` holds its six variables: depth, temperature, salinity, dissolved oxygen as percentage saturation and as concentration, and pH. The sixteen further instrument channels of the earlier delivery are not released.
- The other five tidy files, the summary table, the overview map, the position check and the photograph archives are unchanged.
- Archived on Zenodo as [doi:10.5281/zenodo.24199215](https://doi.org/10.5281/zenodo.24199215); version 1.0.0 is [doi:10.5281/zenodo.23454705](https://doi.org/10.5281/zenodo.23454705).

## 1.0.0

- `make_tidy_tables`: derives the six tidy tables from the five delivered files.
- `summarize` and `overview_map`: the per-campaign summary table and the overview map of the record.
- `check_positions`: reproduces the position check of the quadrats against lidar bathymetry, from the archived evidence or from the EMODnet raster.
- `pack_photographs`: the three photograph archives and `photographs.csv`.
