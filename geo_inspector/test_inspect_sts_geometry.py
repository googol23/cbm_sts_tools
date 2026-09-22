"""Run with python3 -m pytest geo_inspector/test_inspect_sts_geometry.py."""
import csv
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from geo_inspector.inspect_sts_geometry import (
    join_sensors, main, parse_sensor_path, read_grades, ROTATION_FIELDS,
)

HERE = Path(__file__).resolve().parent
PATH = '/TOP_1/sts_v22d_1/Unit00R_1/LadderType0010_101/HalfLadder10t_1/HalfLadder10t_Module01_1/Sensor01_1'


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sensor(path=PATH, size=2.2):
    return dict(node_path=path, x=-20, y=5, z=30, dx=6.2, dy=size, dz=0.03,
                **dict(zip(ROTATION_FIELDS, (1, 0, 0, 0, 1, 0, 0, 0, 1))))


@pytest.mark.parametrize('path,key,name', [
    (PATH, (0, 'R', 3, 'T', 0), 'M0DR1T0'),
    (PATH.replace('Unit00R_1/LadderType0010_101', 'Unit01R_3/LadderType1101_104'),
     (0, 'R', 0, 'T', 0), 'M1UR4T0'),
    (PATH.replace('Unit00R_1/LadderType0010_101', 'Unit04R_9/LadderType0015_401'),
     (3, 'R', 6, 'T', 0), 'M4DR1T0'),
    (PATH.replace('Unit00R_1/LadderType0010_101', 'Unit09L_20/LadderType1024_816'),
     (7, 'L', 7, 'T', 0), 'M9UL16T0'),
])
def test_address_mapping(path, key, name):
    assert parse_sensor_path(path) == (key, name, 0)


def test_legacy_naming():
    path = PATH.replace('Unit00R_1/LadderType0010_101', 'Unit04R_9/LadderType0015_401')
    assert parse_sensor_path(path, 'STS8')[1] == 'M3DR1T0'


def test_geometry_ladder_index_preserves_grade_lookup(tmp_path):
    path = tmp_path / 'sensors.csv'
    prefix = ('/top_1/sts_v22d_1/Unit00L_2/LadderType0101_105/'
              'HalfLadder01b_2/HalfLadder01b_Module')
    rows = [sensor(f'{prefix}{kind:02}_{index + 1}/Sensor{kind:02}_1', size)
            for index, (kind, size) in enumerate(((1, 2.2), (2, 4.2), (3, 6.2), (3, 6.2)))]
    write_csv(path, rows)
    grades = {(0, 'L', 0, 'B', index): (size, grade)
              for index, (size, grade) in enumerate(((2.2, 'C'), (4.2, 'C'), (6.2, 'B'), (6.2, 'B')))}
    joined = join_sensors(path, grades)
    assert [row['module_name'] for row in joined] == [f'M0DL5B{i}' for i in range(4)]
    assert [row['ladder'] for row in joined] == [0] * 4
    assert [row['grade'] for row in joined] == ['C', 'C', 'B', 'B']


def source_rows():
    """Independent fixture from the generator's actual placement and sensor tables.

    Positions are synthetic here; the ROOT integration test checks transforms.
    """
    source = (HERE / 'create_stsgeo_v22d.C').read_text()
    def table(name):
        body = source.split(f'Int_t {name}', 1)[1].split('=', 1)[1].split(';', 1)[0]
        body = re.sub(r'//[^\n]*', '', body)
        return [[int(value.replace(' ', '')) for value in row.split(',')]
                for row in re.findall(r'\{([^{}]+)\}', body)]
    sectors = table('allSectorTypes')
    units = table('allUnitTypes')
    sizes = {1: 2.2, 2: 4.2, 3: 6.2, 4: 12.4}
    for face_index, types in enumerate(units):
        types = [value for value in types if value >= 0]
        station = face_index // 2
        old_unit = (face_index + 1) // 2
        unit = old_unit + (face_index >= 6)
        for slot, ladder_type in enumerate(types):
            if not ladder_type:
                continue
            side = 'R' if slot < len(types) // 2 else 'L'
            layout = ladder_type % 100
            for half_copy, half in enumerate('tb', 1):
                for module, sector in enumerate(filter(None, sectors[layout - 1][:5]), 1):
                    path = (f'/TOP_1/sts_1/Unit{unit:02}{side}_1/'
                            f'LadderType{ladder_type:04}_{(station + 1) * 100 + slot + 1}/'
                            f'HalfLadder{layout:02}{half}_{half_copy}/'
                            f'HalfLadder{layout:02}{half}_Module{sector:02}_{module}/Sensor{sector:02}_1')
                    yield sensor(path, sizes[sector])


def test_entire_supplied_grade_table(tmp_path):
    path = tmp_path / 'sensors.csv'
    rows = list(source_rows())
    write_csv(path, rows)
    grades = read_grades(HERE / 'data/input/uli_new_grades.txt')
    joined = join_sensors(path, grades, include_path=True)
    assert len(joined) == len(grades) == len(rows)
    assert len({row['module_name'] for row in joined}) == len(rows)
    assert {row['grade'] for row in joined} == set('ABCD')
    assert all(row['node_path'].endswith('_1') for row in joined)
    print(f'Validated {len(rows)} sensor/module mappings against supplied grades')


@pytest.mark.parametrize('change,error', [
    ({'dy': 4.2}, 'size mismatch'),
    ({'x': float('nan')}, 'Nonfinite'),
    ({'dz': -1}, 'Nonpositive'),
    ({'node_path': PATH.replace('Unit00R', 'Unit02R')}, 'disagree'),
])
def test_reject_invalid_sensor(tmp_path, change, error):
    row = sensor()
    row.update(change)
    path = tmp_path / 'sensors.csv'
    write_csv(path, [row])
    with pytest.raises(ValueError, match=error):
        join_sensors(path, {(0, 'R', 3, 'T', 0): (2.2, 'C')})


def test_duplicate_and_missing(tmp_path):
    path = tmp_path / 'sensors.csv'
    grades = {(0, 'R', 3, 'T', 0): (2.2, 'C')}
    write_csv(path, [sensor(), sensor()])
    with pytest.raises(ValueError, match='one sensor'):
        join_sensors(path, grades)
    write_csv(path, [sensor()])
    with pytest.raises(ValueError, match='No grade'):
        join_sensors(path, {})
    grades[(0, 'R', 3, 'B', 0)] = (2.2, 'B')
    with pytest.raises(ValueError, match='no sensor'):
        join_sensors(path, grades)


def test_cli_and_preserve_output_on_failure(tmp_path):
    path = tmp_path / 'sensors.csv'
    output = tmp_path / 'nested' / 'output' / 'joined.csv'
    write_csv(path, list(source_rows()))
    assert main(['--sensor-csv', str(path), '--output', str(output), '--include-path']) == 0
    previous = output.read_bytes()
    write_csv(path, [sensor()])
    assert main(['--sensor-csv', str(path), '--output', str(output)]) == 1
    assert output.read_bytes() == previous


@pytest.mark.parametrize('arguments,filename', [
    ([], 'module_geometry_grades.csv'),
    (['--output', 'custom.csv'], 'custom.csv'),
])
def test_output_directory_from_other_working_directory(tmp_path, monkeypatch, arguments, filename):
    import geo_inspector.inspect_sts_geometry as inspector

    output_dir = tmp_path / 'subproject' / 'data' / 'output'
    monkeypatch.setattr(inspector, 'OUTPUT_DIR', output_dir)
    monkeypatch.chdir(tmp_path)
    source = tmp_path / 'sensors.csv'
    write_csv(source, list(source_rows()))
    assert main(['--sensor-csv', str(source), *arguments]) == 0
    assert (output_dir / filename).is_file()
    assert not (tmp_path / filename).exists()


def test_duplicate_grades(tmp_path):
    path = tmp_path / 'grades.txt'
    path.write_text('station(unit) l/r ladder t/b module size grade\n' + '0 R 3 T 0 2.2 C\n' * 2)
    with pytest.raises(ValueError, match='Duplicate grade'):
        read_grades(path)


@pytest.mark.skipif(shutil.which('root') is None, reason='External ROOT environment is not set')
def test_root_transform_and_export_formats(tmp_path):
    # Real ROOT fixture: nonzero shape origin, nested translation and 90 degree rotation.
    fixture = tmp_path / 'fixture.C'
    fixture.write_text('''
#include <TGeoManager.h>
#include <TGeoVolume.h>
#include <TGeoMatrix.h>
#include <TGeoBBox.h>
#include <TFile.h>
void fixture() {
    auto* geo = new TGeoManager("fixture", "fixture");
    auto* top = new TGeoVolumeAssembly("TOP");
    auto* sts = new TGeoVolumeAssembly("sts");
    auto* unit = new TGeoVolumeAssembly("Unit00R");
    auto* ladder = new TGeoVolumeAssembly("LadderType0010");
    auto* half = new TGeoVolumeAssembly("HalfLadder10t");
    auto* module = new TGeoVolumeAssembly("HalfLadder10t_Module01");
    double origin[3] = {1, 2, 3};
    auto* sensor = new TGeoVolume("Sensor01", new TGeoBBox("box", 3.1, 1.1, .015, origin));
    geo->SetTopVolume(top);
    top->AddNode(sts, 1, new TGeoTranslation(0, 0, 59.5));
    sts->AddNode(unit, 1, new TGeoTranslation(10, 20, 30));
    auto* rotation = new TGeoRotation(); rotation->RotateZ(90);
    unit->AddNode(ladder, 101, new TGeoCombiTrans(0, 0, 0, rotation));
    ladder->AddNode(half, 1);
    half->AddNode(module, 1, new TGeoTranslation(4, 5, 6));
    module->AddNode(sensor, 1);
    geo->CloseGeometry();
    { TFile file("manager.root", "RECREATE"); geo->Write(); }
    sts->Export("volume.root");
    { TFile file("volume.root", "UPDATE"); TGeoTranslation placement("sts_trans",0,0,59.5); placement.Write(); }
}
''')
    subprocess.run(['root', '-l', '-b', '-q', str(fixture)], cwd=tmp_path, check=True)
    macro = (HERE / 'extract_sts_sensors.C').resolve()
    results = []
    for kind in ('manager', 'volume'):
        subprocess.run(['root', '-l', '-b', '-q', f'{macro}("{kind}.root","{tmp_path / (kind + ".csv")}")'],
                       cwd=tmp_path, check=True)
        with (tmp_path / f'{kind}.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 1
        row = rows[0]
        assert [float(row[key]) for key in ('x', 'y', 'z', 'dx', 'dy', 'dz')] == pytest.approx(
            [3, 25, 98.5, 6.2, 2.2, .03])
        results.append([float(row[key]) for key in ROTATION_FIELDS])
    assert results[0] == pytest.approx(results[1])
