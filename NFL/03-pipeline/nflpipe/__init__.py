"""nflpipe: the NFL-Analysis fantasy-football data pipeline.

Downloads public nflverse data, derives long-touchdown counts and team D/ST rows,
scores every league defined in ``02-config/`` and publishes plain CSV files to
``04-data/`` for the Excel workbook. The published data is derived from nflverse data, licensed
CC BY 4.0 (``DATA-LICENSE.md`` at the repository root). The file formats are specified in
``../CONTRACTS.md``. Run time uses the Python standard library only (decision D-025).
"""

# 1.2.0 (2026-11-20): new derived metric dst_points_allowed_excl_def, ESPN's points allowed (D-038).
pipeline_version = "1.2.0"

# Version of the published file formats (CONTRACTS.md, "data contract version").
data_contract_version = "1"

# Attribution written to status.csv with every publish (the data is derived from nflverse, CC BY 4.0).
data_source = ("nflverse, https://github.com/nflverse/nflverse-data (modified: see DATA-LICENSE.md "
               "at the repository root)")
data_license = "CC BY 4.0, https://creativecommons.org/licenses/by/4.0/"
