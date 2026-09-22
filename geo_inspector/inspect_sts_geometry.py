#!/usr/bin/env python3
"""Extract v22d sensor placements with external ROOT and join module grades."""
import argparse
import csv
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.sts_naming import build_module_name_prefix

PROJECT_DIR = Path(__file__).resolve().parent
INPUT_DIR = PROJECT_DIR / 'data' / 'input'
OUTPUT_DIR = PROJECT_DIR / 'data' / 'output'

# ConstructUnit removes -1 slots, retains 0 slots, and numbers from negative x.
STATION_WIDTHS = (8, 12, 12, 14, 14, 14, 16, 16)
PATH_PATTERN = re.compile(
    r"/Unit(?P<unit>\d{2})(?P<side>[RL])_\d+"
    r"/LadderType(?P<type>\d{4})_(?P<copy>\d+)"
    r"/HalfLadder\d+[tb]_(?P<half>[12])"
    r"/HalfLadder\d+[tb]_Module\d+_(?P<module>\d+)"
    r"/Sensor\d+_(?P<sensor>\d+)$"
)
NUMERIC_FIELDS = ('x', 'y', 'z', 'dx', 'dy', 'dz')
ROTATION_FIELDS = tuple(f'r{i}{j}' for i in range(3) for j in range(3))


def parse_sensor_path(path, naming_version='STS3_5'):
    match = PATH_PATTERN.search(path)
    if not match:
        raise ValueError(f'Unsupported v22d sensor path: {path}')
    values = match.groupdict()
    station = int(values['copy']) // 100 - 1
    slot = int(values['copy']) % 100 - 1
    if not 0 <= station < len(STATION_WIDTHS):
        raise ValueError(f'Invalid station copy number: {path}')
    width = STATION_WIDTHS[station]
    side = values['side']
    if not 0 <= slot < width or (slot < width // 2) != (side == 'R'):
        raise ValueError(f'Ladder copy number and unit side disagree: {path}')
    ladder = width // 2 - 1 - slot if side == 'R' else slot - width // 2
    ladder_type = int(values['type'])
    if not 0 < ladder_type < 2000:
        raise ValueError(f'Unsupported ladder type: {path}')
    face = 'U' if ladder_type >= 1000 else 'D'
    old_unit = station + (face == 'U')
    physical_unit = old_unit + (old_unit > 3 or (old_unit == 3 and face == 'D'))
    if int(values['unit']) != physical_unit:
        raise ValueError(f'Unit and station/face disagree for v22d: {path}')
    half = 'T' if values['half'] == '1' else 'B'
    module = int(values['module']) - 1
    sensor = int(values['sensor']) - 1
    if not 0 <= module <= 9 or sensor < 0:
        raise ValueError(f'Invalid module/sensor copy: {path}')
    # Names retain the geometry's one-based slot; grades use the side-relative index.
    name = build_module_name_prefix(old_unit, face, side, slot + 1, half, module,
                                    version=naming_version)
    return (station, side, ladder, half, module), name, sensor


def read_grades(path):
    grades = {}
    with Path(path).open() as stream:
        header = next(stream, '').split()
        if header != ['station(unit)', 'l/r', 'ladder', 't/b', 'module', 'size', 'grade']:
            raise ValueError('Unexpected grade table header')
        for line_number, line in enumerate(stream, 2):
            if not line.strip():
                continue
            fields = line.split()
            if len(fields) != 7:
                raise ValueError(f'Grade line {line_number}: expected seven columns')
            station, side, ladder, half, module, size, grade = fields
            key = (int(station), side, int(ladder), half, int(module))
            size = float(size)
            if (not 0 <= key[0] < 8 or side not in ('L', 'R') or
                    not 0 <= key[2] < STATION_WIDTHS[key[0]] // 2 or
                    half not in ('T', 'B') or not 0 <= key[4] <= 9 or
                    not math.isfinite(size) or size <= 0 or not grade):
                raise ValueError(f'Invalid grade line {line_number}: {line.strip()}')
            if key in grades:
                raise ValueError(f'Duplicate grade key at line {line_number}: {key}')
            grades[key] = (size, grade)
    if not grades:
        raise ValueError('Grade table is empty')
    return grades


def join_sensors(sensor_csv, grades, naming_version='STS3_5', include_path=False):
    result, seen = [], set()
    with Path(sensor_csv).open(newline='') as stream:
        reader = csv.DictReader(stream)
        required = {'node_path', *NUMERIC_FIELDS, *ROTATION_FIELDS}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f'Sensor CSV requires columns: {sorted(required)}')
        for raw in reader:
            path = raw['node_path']
            key, name, sensor = parse_sensor_path(path, naming_version)
            # The supplied v22d generator has exactly one sensor per module.
            if key in seen or sensor != 0:
                raise ValueError(f'Expected one sensor per module: {path}')
            seen.add(key)
            if key not in grades:
                raise ValueError(f'No grade for module {name}, table key {key}: {path}')
            numbers = {field: float(raw[field]) for field in (*NUMERIC_FIELDS, *ROTATION_FIELDS)}
            if not all(math.isfinite(value) for value in numbers.values()):
                raise ValueError(f'Nonfinite geometry values: {path}')
            if any(numbers[field] <= 0 for field in ('dx', 'dy', 'dz')):
                raise ValueError(f'Nonpositive sensor dimensions: {path}')
            size, grade = grades[key]
            if not math.isclose(numbers['dy'], size, rel_tol=0, abs_tol=1e-6):
                raise ValueError(f'Sensor size mismatch for {name}: geometry {numbers["dy"]}, grade table {size}')
            row = dict(module_name=name, station=key[0], side=key[1], ladder=key[2],
                       half=key[3], module=key[4], grade=grade, **numbers)
            if include_path:
                row['node_path'] = path
            result.append(row)
    missing = grades.keys() - seen
    if missing:
        raise ValueError(f'{len(missing)} grade entries have no sensor; examples: {sorted(missing)[:5]}')
    return sorted(result, key=lambda row: (row['station'], row['side'], row['ladder'], row['half'], row['module']))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--geometry', type=Path, help='v22d ROOT geometry file')
    inputs.add_argument('--sensor-csv', type=Path, help='CSV already produced by the ROOT macro')
    parser.add_argument('--grades', type=Path, default=INPUT_DIR / 'uli_new_grades.txt')
    parser.add_argument('--output', type=Path, default=Path('module_geometry_grades.csv'),
                        help='Output filename relative to geo_inspector/data/output, or an absolute path')
    parser.add_argument('--naming-version', choices=('STS8', 'STS3_5'), default='STS3_5')
    parser.add_argument('--include-path', action='store_true')
    parser.add_argument('--root', default='root', help='ROOT executable from your external environment')
    args = parser.parse_args(argv)
    if not args.output.is_absolute():
        args.output = OUTPUT_DIR / args.output
    try:
        for source in (args.geometry, args.sensor_csv, args.grades):
            if source and source.resolve() == args.output.resolve():
                raise ValueError('Output must differ from all input files')
        grades = read_grades(args.grades)
        with tempfile.TemporaryDirectory(prefix='sts-inspector-') as directory:
            sensor_csv = args.sensor_csv
            if args.geometry:
                if not args.geometry.is_file():
                    raise ValueError(f'Geometry file does not exist: {args.geometry}')
                root = shutil.which(args.root)
                if root is None:
                    raise ValueError('ROOT executable not found; set up your ROOT environment first or use --root')
                sensor_csv = Path(directory) / 'sensors.csv'
                # Fixed wrapper avoids embedding user paths into ROOT command-line syntax.
                macro = Path(__file__).with_name('extract_sts_sensors.C').resolve()
                wrapper = Path(directory) / 'run_extract.C'
                wrapper.write_text(
                    f'#include {json.dumps(str(macro))}\n'
                    'void run_extract() { extract_sts_sensors('
                    f'{json.dumps(str(args.geometry.resolve()))}, {json.dumps(str(sensor_csv))}); }}\n'
                )
                subprocess.run([root, '-l', '-b', '-q', str(wrapper)], check=True)
            rows = join_sensors(sensor_csv, grades, args.naming_version, args.include_path)
        # Only replace the destination after extraction and every join check succeeds.
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', newline='', dir=args.output.resolve().parent,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            try:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
                stream.close()
                temporary.replace(args.output)
            finally:
                temporary.unlink(missing_ok=True)
        print(f'Wrote {len(rows)} modules to {args.output} (cm, full sensor dimensions)')
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'inspect_sts_geometry: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
