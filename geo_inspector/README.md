# STS geometry and module grades

Use the ROOT environment you normally source outside these tools. Neither tool
installs ROOT, sources a setup script, nor requires FairRoot to inspect a saved
geometry. Python 3.10+ and the Python standard library are sufficient; PyROOT is
not required. Keep this directory alongside `../utils/sts_naming.py`.

From the repository root:

```bash
python3 geo_inspector/inspect_sts_geometry.py \
  --geometry geo_inspector/data/input/sts_v22d_geo.root \
  --include-path
```

The subproject keeps supplied files in `geo_inspector/data/input` and generated
files in `geo_inspector/data/output`. Default paths are relative to the script or
macro location, independent of the working directory. Output directories are
created automatically.

- `inspect_sts_geometry.py` writes `data/output/module_geometry_grades.csv`.
- `extract_sts_sensors.C` writes `data/output/sensors.csv` when run separately.
- `create_stsgeo_v22d.C` writes all three generated ROOT files and the `.geo.info`
  file to `data/output` (this generator still needs its usual FairRoot setup).
- `inspect_module_table.py` reads `data/output/module_geometry_grades.csv` by
  default and prints to the terminal; it does not create a file.

For the extractor and Python join script, custom relative output names (such as
`--output custom.csv`) also resolve under `data/output`. An explicit absolute
output path overrides that directory. Explicit input paths remain relative to
the working directory. The Python script's intermediate sensor CSV is temporary
and is removed after the join; run the macro separately to retain it.

`--root /path/to/root` selects a specific externally configured executable.
The script inherits your environment. It runs the macro in batch mode and joins
the extracted placements to the grades. No geometry input is modified.

The two stages can also run separately:

```bash
root -l -b -q 'geo_inspector/extract_sts_sensors.C("geo_inspector/data/input/sts_v22d_geo.root")'
python3 geo_inspector/inspect_sts_geometry.py \
  --sensor-csv geo_inspector/data/output/sensors.csv --include-path
```

The macro writes geometry information only; the Python script supplies the names
and grades. The default grade file is `data/input/uli_new_grades.txt` within the
subproject.

## Coordinates and output

Each output row represents one module's sensor, with these CSV columns:

- `module_name`: positional prefix using the geometry ladder index, e.g. `M0DL5B0`.
- `station,side,ladder,half,module`: the original grade-table lookup key.
- `grade`: the grade table's label, preserved verbatim.
- `x,y,z`: sensor box centre in global coordinates, in **cm**.
- `dx,dy,dz`: **full sensor dimensions** in local sensor axes, in **cm**;
  these are twice ROOT's `GetDX/GetDY/GetDZ`, excluding cables and supports.
- `r00` through `r22`: row-major local-to-global orientation matrix. For a
  displacement from the sensor centre, `global = centre + R * displacement`.
- `node_path`: included with `--include-path`; always present in the macro's CSV.

Dimensions remain intrinsic dimensions even when the sensor is rotated. They
are not global axis-aligned bounding-box extents. The box origin, every ancestor
placement, and sensor placement are included when calculating the centre.
Transforms use ROOT's [TGeoMatrix API](https://root.cern.ch/doc/master/classTGeoMatrix.html).

The macro accepts the generator's full `TGeoManager` export and its single-volume
exports with a saved placement matrix. For the latter, it applies that matrix
(including the generator's 59.5 cm z translation) exactly once. For manager files,
the placement already belongs to the hierarchy. A volume-only file without a
placement matrix is rejected because its global placement is unknown. A
volume-only debug path starts at the exported volume; a manager debug path starts
at the real top node.

## Mapping the v22d geometry to grades

The implementation targets the hierarchy in the supplied `create_stsgeo_v22d.C`.
It intentionally rejects incompatible naming layouts, including later geometries
that replace `LadderTypeNNNN` with serial-number-based ladder names.

`ConstructUnit` encodes the one-based station and transverse slot in the ladder
copy number: `station * 100 + slot`. Its slot counts, after removing `-1` entries
but retaining empty `0` slots, are `8,12,12,14,14,14,16,16`. Slots run from negative
to positive x. R is the negative-x half; L is the positive-x half. The grade-table
ladder index counts outward from the beam line, starting at zero on each side.
That side-relative index is used only for grade lookup and the CSV `ladder`
column. Module names retain the encoded one-based slot (`copy_number % 100`):
`LadderType0101_105` gives `M0DL5…`, while its grade-table ladder index is 0.

Ladder types below 1000 have face D; types at or above 1000 have face U, as in the
generator's `allUnitTypes` table. For zero-based station `s`, the old unit index is
`s` on face D and `s+1` on face U. The shared `build_module_name_prefix` function
then applies the STS3_5 renumbering. `--naming-version STS8` selects the old output
names while still reading the supplied v22d geometry. The geometry unit name is
cross-checked against its expected STS3_5 unit.

Half-ladder copies 1 and 2 map to T and B. Module copy numbers minus one provide
the module index: the `ModuleNN` part denotes a sensor type, not that index.

Only the positional prefix can be reconstructed. Geometry ladder indices 10–16
occupy two digits, so these prefixes do not follow the single-digit ladder format
expected by the existing manufacturing-label validators/address parsers. The full
15-character manufacturing label requires serial/manufacturing information that
neither the geometry nor the supplied grade table contains. No suffix is invented.

The supplied generator places one sensor per module, including a single 12.4 cm
sensor for long modules. Multiple sensors for one module are rejected. Every grade
must match exactly one sensor and its `size` must match the full local y dimension
within 1e-6 cm. Duplicate grades, missing grades, unused grades, incompatible paths,
and invalid dimensions cause a nonzero exit. The final CSV is replaced only after
all checks pass. Subset geometries require a correspondingly reduced grade table.

## Station plots

Use a Python environment with Matplotlib installed (ROOT and pandas are not
required for plotting):

```bash
python3 geo_inspector/plot_module_grades.py
python3 geo_inspector/plot_module_grades.py --dpi 150
```

The script reads `data/output/module_geometry_grades.csv` by default and writes
eight images, `data/output/station_0_xy.png` through `station_7_xy.png`, using the
table's zero-based station numbers. An optional positional argument selects
another CSV. `--output-dir plots` writes under `data/output/plots`; an absolute
directory overrides that location. Rerunning replaces the same plot filenames.

Each sensor is drawn using its full local x/y dimensions, global centre, and
orientation matrix. The sensor face is projected onto XY, with positive x to the
right and positive y upward; z separation is collapsed, so projected modules
can overlap. All plots use equal axis scales, common limits, centimetre labels,
and a grade legend. PNG resolution defaults to 300 DPI (3000 × 3000 pixels).

Edit `GRADE_PALETTE` in `plot_module_grades.py` to change colours or add grades.
The initial palette uses green for A, blue for B, amber for C, and red for D.
An unknown grade is rejected with a message to extend the palette. Missing
stations or invalid geometry values are rejected before plots are written.

## Validation

To inspect the resulting CSV with pandas:

```bash
python3 geo_inspector/inspect_module_table.py --rows 20
```

Use a Python environment with pandas installed. Edit `PRINT_COLUMNS` in
`inspect_module_table.py` to select the printed columns and their order. All
columns are loaded into the DataFrame using the CSV header; the selection only
affects printing. The inspector first lists all available columns, then prints
the first 10 rows by default, without the DataFrame index. Set `--rows N` to
change the limit, or edit the default `PRINT_ROWS` constant. Zero is allowed;
negative limits are rejected. All source rows are still loaded into the DataFrame.

```bash
python3 -m pytest geo_inspector/test_inspect_sts_geometry.py
python3 -m pytest geo_inspector/test_plot_module_grades.py
```

Tests compare all 876 supplied grade entries with placements reconstructed from
the generator's actual unit/sector tables, and cover naming, invalid input, and
output preservation. These reconstructed rows use synthetic positions; they do
not substitute for ROOT coordinate checks. When `root` is on PATH, an additional
integration test builds a tiny real geometry and checks nested transformations,
a rotated sensor with a nonzero box origin, and agreement between manager and
volume exports. That test is skipped explicitly when ROOT is unavailable.
