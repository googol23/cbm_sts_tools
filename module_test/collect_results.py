import argparse
import os
import re
import subprocess
import textwrap
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Iterator

from datetime import datetime
import logging

log_dir = Path("log/")
log_dir.mkdir(exist_ok=True)

logger = logging.getLogger("CollectResults")
logger.setLevel(logging.DEBUG)
logger.handlers.clear()

formatter = logging.Formatter(
    "%(asctime)s %(levelname)-8s %(message)s"
)

# timestamp prefix for file name
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = log_dir / f"{timestamp}_collect_result.log"

# File: DEBUG and above
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

# Terminal: INFO and above
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

from utils import sts_naming

from .index_builder import get_all_files, init_db
from .module_test import ModuleTestResult, ValueErrorUnit



# cbmstsgw02
# stsdcs03
# TEST_RESULT_PATH="/home/cbm/cbmsoft/emu_test_module_arr/python/module_files"

PATH_PATTERN = re.compile(
    r"""
    ^
    (?P<ladder>[^/]+)/
    (?P<module>[^/]+)/
    pscan_files/
    module_test_(?P<module_file>[^/]+)\.txt
    $
    """,
    re.VERBOSE,
)

TEST_RESULT_PATH = "test_result/"
CHANNEL_MASK_FILE = "channelMask.par"
CHARGE_CALIB_FILE = "chargeCalibration.par"
ADDRESS_DUMP_FILE = "STS_NAME_TO_ADDRESS_DUMP.dump"


def serve_sshfs(host: str, remote_path: str, mount_point: str = "test_result") -> Path:
    """
    Ensure that `remote_path` on `host` is mounted at `mount_point`.

    Returns
    -------
    Path
        The local mount point.
    """
    mount_point = Path(mount_point)
    mount_point.mkdir(parents=True, exist_ok=True)

    # Already mounted?
    result = subprocess.run(
        ["mountpoint", "-q", str(mount_point)],
        check=False,
    )

    if result.returncode == 0:
        logger.info("Mount point is busy!!!")
        return Path(mount_point)

    # Mount it
    subprocess.run(
        [
            "sshfs",
            f"{host}:{remote_path}",
            str(mount_point),
        ],
        check=True,
    )

    # Verify
    result = subprocess.run(
        ["mountpoint", "-q", str(mount_point)],
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Failed to mount {host}:{remote_path} on {mount_point}")

    return Path(mount_point)

def process(path: str | Path) -> None | tuple[int, ModuleTestResult | None]:
    """
    Process a single test file
    Source can be a local file or a remote file if remote_host is provided.
    SSH configuration is assumed
    """
    module_name = Path(path).parent.parent.name

    cbm_sts_address = sts_naming.convert_to_cbm_sts_address(module_name)

    try:
        module_test_result = ModuleTestResult.from_file(str(path))

    except Exception as e:
        logger.info(f"{e}. Discarding file")
        return None

    logger.debug(f"{path} -> Done")
    return cbm_sts_address, module_test_result


def asic_par_input(
    address: int, side: int, asic_idx: int, enc: float, gain: float
) -> str:
    modSide = side
    asicIdx = asic_idx
    nChannels = 128
    nAdc = 31
    dynRange = gain * nAdc
    threshold = 4 * enc
    timeResol = 5
    deadTime = 200
    noise = enc
    znr = 3.9789e-3

    return (
        f"0x{address:x}\t"
        f"{modSide:>7}\t"
        f"{asicIdx:>7}\t"
        f"{nChannels:>9}\t"
        f"{nAdc:>4}\t"
        f"{dynRange:>8}\t"
        f"{threshold:>9}\t"
        f"{timeResol:>9}\t"
        f"{deadTime:>8}\t"
        f"{noise:>5}\t"
        f"{znr:>3}"
    )


if __name__ == "__main__":
    description = textwrap.dedent("""
        Proccess module test files to generate optionally
        \t- inactive channels parameter files
        \t- charge calibration files
    """).expandtabs(4)

    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("--path", help="Base path to the module test folders")
    parser.add_argument(
        "--host",
        default=None,
        help="SSH host (if omitted, provided path is assumed local)",
    )
    parser.add_argument(
        "--db",
        default="module_test/file_index.db",
        help="Data base for files index (avoid file ssytem scanning)",
    )

    args = parser.parse_args()

    try:
        root = Path(TEST_RESULT_PATH)

        if not root.exists():
            raise ValueError(f"Directory does not exist: {root}")

        conn = init_db(args.db)
        paths = get_all_files(conn)

        # Mount remoted if needed and provide path relative to mount point
        if args.host is not None:
            mount_point = serve_sshfs(args.host, args.path)
            mount_point = "test_result/"

            paths = [mount_point / Path(rf).relative_to(args.path) for rf in paths]


        logger.info(f"Found {len(paths)} test file to be collected...")
        logger.info("Starting processing files ...")

        with ThreadPoolExecutor(max_workers=32) as executor:
            results = executor.map(process, paths)

        logger.info(f"Inactive channels will be written to: {CHANNEL_MASK_FILE}")
        logger.info(f"ASIC configuration will be written to: {CHARGE_CALIB_FILE}")
        channel_mask_file = open(CHANNEL_MASK_FILE, "w")
        charge_calib_file = open(CHARGE_CALIB_FILE, "w")

        charge_calib_file.write(
            textwrap.dedent("""
            brief Constructor with parameters
            @param modSide Sensor side: 1 = p-side
                                        0 = n-side
                                       -1 = both sides
            @param nChannels   Number of readout channels
            @param nAdc        Number of ADC channels
            @param dynRange    Dynamic range of ADC [e]
            @param threshold   ADC threshold [e]
            @param timeResol   Time resolution [ns]
            @param deadTime    Single-channel dead time [ns]
            @param noise       Noise RMS [e]
            @param znr         Zero-crossing noise rate [1/ns]

            if AsicIdx == -1: global module calibration

            ModAddress    modSide     AsicIdx  nChannels  nAdc  dynRange  threshold  timeResol  deadTime  noise  znr
        """)
        )

        for res in results:
            if res is None:
                continue

            address, module_test_result = res

            if module_test_result is None:
                continue

            # Write inactive channel lines
            faulty_channels = [chn for chn in module_test_result.list_broken_channels_n_side]
            faulty_channels.extend([2047 - chn for chn in module_test_result.list_broken_channels_p_side])
            for chn in faulty_channels:
                channel_mask_file.write(f"{address} {chn}\n")

            # Write calibration line
            enc_n_side = module_test_result.average_adc_enc_n_side
            enc_p_side = module_test_result.average_adc_enc_p_side
            gain_n_side = module_test_result.average_adc_gain_n_side
            gain_p_side = module_test_result.average_adc_gain_p_side

            charge_calib_file.write(asic_par_input(address, 0, -1, enc_n_side.value, gain_n_side.value) + "\n")
            charge_calib_file.write(asic_par_input(address, 1, -1, enc_p_side.value, gain_p_side.value) + "\n")

        logger.info(f"Dumping address building to: {ADDRESS_DUMP_FILE}")
        with open(ADDRESS_DUMP_FILE, "w") as dump:
            for k, v in sts_naming.STS_NAME_TO_ADDRESS_DUMP.items():
                dump.write(f"{k}\t{v}\n")

    except KeyboardInterrupt:
        logger.info("Aborting ...")
    except Exception as e:
        logger.warning(e)
