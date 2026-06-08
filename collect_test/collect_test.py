import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterator

import sts_naming

# cbmstsgw02
# stsdcs03
# TEST_RESULT_PATH="/home/cbm/cbmsoft/emu_test_module_arr/python/module_files"
TEST_RESULT_PATH = "test_result/"
CHANNEL_MASK_FILE = "channel_mask.txt"
ADDRESS_DUMP_FILE = "STS_NAME_TO_ADDRESS_DUMP.dump"

def proccess_module_test_file(in_file: str) -> list[int]:
    """This method scans the module test output file (ASCI)
    it looks for the faulty channel list lines and collect the channel numbers

    channels for n-side has direct mapping
    channels for p-side are calculated as 1024 - channel_id

    Each faulty channel in the list contains information about the cuase encluse in '( )'
    This part is stripped away to collect the channel id

    return: a list of int, mapped to the module channels (0-2047)
    """
    pattern = "LIST_BROKEN_CHANNELS"
    faulty_channels = []

    with open(in_file) as file:
        lines = file.readlines()

        for line in lines:
            if pattern not in line:
                continue

            info, values = line.strip().split(":")

            if len(values.strip()) == 0:
                continue

            channels_id = [
                int(v.split("(")[0].strip()) for v in values.split(",") if len(v) != 0
            ]
            if "P-side" in info:
                channels_id = [2047 - chn for chn in channels_id]

            faulty_channels.extend(channels_id)

    return faulty_channels


def find_module_test_files(
    root_dir: str,
) -> Iterator[str]:
    """
    Recursively search for files matching:
        module_test_<MODULE_NAME>.txt

    Parameters
    ----------
    root_dir : str
        Root directory to start searching from.

    Yields
    ------
    str
        Full path of each matching file.
    """
    root = Path(root_dir)

    if not root.exists():
        raise ValueError(f"Directory does not exist: {root_dir}")

    for path in root.rglob("module_test_*.txt"):
        if path.is_file() and len(path.parts) == 5:
            ladder_name = path.parts[1]
            module_name = path.parts[2]

            if not sts_naming.is_valid_label(
                ladder_name, sts_naming.LADDER_NAME_PATTERN
            ):
                # print("parts:", path.parts)
                # print("Expected a ladder name:", ladder_name)
                continue

            if not sts_naming.is_valid_label(
                module_name, sts_naming.MODULE_NAME_PATTERN
            ):
                # print("parts:", path.parts)
                # print("Excpected a module name:", ladder_name)
                continue

            if path.parts[3] != "pscan_files":
                # print("parts:", path.parts)
                continue

            module_name_in_test_file = (
                path.name.split("/")[-1].split("_")[-1].split(".")[0]
            )
            if not sts_naming.is_valid_label(
                module_name_in_test_file, sts_naming.MODULE_NAME_PATTERN
            ):
                print("Unexpected test file name:", path.name, module_name_in_test_file)

            yield str(path)


def process(path: Path) -> None | tuple[int,list[int]]:
    # print(f"Check {path}\n...")
    """
        Process a single test file
        Ensure the path of the file follows the stamdarize directory tree:
            .../<LADDER_NAME>/<MODULE_NAME>/pscan_files/"module_test_<MODULE_NAME>.txt
    """
    if not path.is_file() or len(path.parts) < 4:
        return None

    ladder_name = path.parts[1]
    module_name = path.parts[2]

    if not sts_naming.is_valid_label(ladder_name, sts_naming.LADDER_NAME_PATTERN):
        # print("parts:", path.parts)
        # print("Expected a ladder name:", ladder_name)
        return None

    # if not sts_naming.is_valid_label(module_name, sts_naming.MODULE_NAME_PATTERN):
    if not sts_naming.is_valid_module_name(module_name):
        # print("parts:", path.parts)
        # print("Excpected a module name:", ladder_name)
        return None

    if path.parts[3] != "pscan_files":
        # print("parts:", path.parts)
        return None

    module_name_in_test_file = path.name.split("/")[-1].split("_")[-1].split(".")[0]
    if not sts_naming.is_valid_label(
        module_name_in_test_file, sts_naming.MODULE_NAME_PATTERN
    ):
        # print("Unexpected test file name:", path.name, module_name_in_test_file)
        return None

    file_path = str(path)
    module_name = file_path.split("/")[-1].split("_")[-1].split(".")[0]
    cbm_sts_address = sts_naming.convert_to_cbm_sts_address(module_name)
    faulty_channels = proccess_module_test_file(file_path)

    return cbm_sts_address, faulty_channels


if __name__ == "__main__":

    try:
        root = Path(TEST_RESULT_PATH)

        if not root.exists():
            raise ValueError(f"Directory does not exist: {root}")

        paths = list(root.rglob("module_test_*.txt"))
        print(f"Foun {len(paths)} test file to be collected...")
        print("Starting processing files ...")

        with ThreadPoolExecutor(max_workers=32) as executor:
            results = executor.map(process, paths)

        print("Writing channel mask to {CHANNEL_MASK_FILE}")
        with open(CHANNEL_MASK_FILE, "w") as o_file:
            for res in results:
                if res is None:
                    continue
                address, faulty_channels = res
                for chn in faulty_channels:
                    o_file.write(f"{address} {chn}\n")

        print(f"Dumping address building to: {ADDRESS_DUMP_FILE}")
        with open(ADDRESS_DUMP_FILE, "w") as dump:
            for k, v in sts_naming.STS_NAME_TO_ADDRESS_DUMP.items():
                dump.write(f"{k}\t{v}\n")

    except KeyboardInterrupt:
        print("Aborting...")
