# First look at AgERA5 heat extremes (2026-11-20)

Scripts and printed results behind sections 8 and 9 of
[docs/agera5-vs-stations.md](../../docs/agera5-vs-stations.md): the effective
number of independent cells in a window (`hx_neff.py`, `hx_neff.txt`) and the
long-term behaviour at single cells (`hx_analyse.py`, `hx_results.txt`).

They were written as one-off checks. `hx_extract.py` and `hx_extract2.py` read
the raw AgERA5 files and write `hx_cells.npz`, which the others load from the
working directory; that file is not in the repository.
