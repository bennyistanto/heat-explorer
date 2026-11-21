#!/usr/bin/env bash
# Run Python from the miniforge `climate` env with the env's DLL folders on PATH.
#
# Why: calling envs/climate/python.exe by full path without activation leaves
# Library/bin off PATH, so numpy cannot load its LAPACK DLL. Any call that
# reaches LAPACK (np.polyfit, np.linalg.lstsq, np.cov, np.corrcoef) then kills
# the interpreter with no message (Windows exception 0xc06d007f, exit 127).
# Measured 2026-11-20. Also sets GDAL_DATA and PROJ_DATA, which pyogrio warns
# about when the env is not activated.
#
# Usage (Git Bash):  bash tools/py.sh script.py [args]
#                    bash tools/py.sh -c "import numpy; ..."
ENV_DIR="/c/Users/benny/miniforge3/envs/climate"
export PATH="$ENV_DIR:$ENV_DIR/Library/bin:$ENV_DIR/Library/mingw-w64/bin:$ENV_DIR/Scripts:$PATH"
export GDAL_DATA="C:/Users/benny/miniforge3/envs/climate/Library/share/gdal"
export PROJ_DATA="C:/Users/benny/miniforge3/envs/climate/Library/share/proj"
exec "$ENV_DIR/python.exe" "$@"
