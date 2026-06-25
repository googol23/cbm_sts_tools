import re
from pathlib import Path

NAMING_VERSION = [
    "STS8",
    "STS3_5",
]

# Compiled once for efficiency
# i.e. M7UR2T3011393A2
MODULE_NAME_PATTERN = re.compile(
    r"^"
    r"M"  # 1
    r"\d"  # 2
    r"[UD]"  # 3
    r"[LR]"  # 4
    r"\d"  # 5
    r"[TB]"  # 6
    r"\d{6}"  # 7–12
    r"\d"  # 13
    r"[ABCD]"  # 14
    r"\d"  # 15
    r"$"
)

LADDER_NAME_PATTERN = re.compile(
    r"^"  # Start
    r"L"  # 1
    r"\d"  # 2
    r"[UD]"  # 3
    r"[LR]"  # 4
    r"\d{6}"  # Positions 5-10
    r"$"  # End
)

def build_module_name_prefix(
    unit:int,
    face:str,
    side:str,
    ladder:int,
    halfladder:str,
    index:int,
    version:str | None = "STS3_5" 
) -> str | None:
    
    if version not in NAMING_VERSION:
        print(f"Unknow naming version: falling back to latest {NAMING_VERSION[-1]}")

    if version == "STS8":
        return f"M{unit}{face}{side}{ladder}{halfladder}{index}"

    if version == "STS3_5":
        if (unit == 3 and face == "D") or unit > 3:
            return f"M{unit+1}{face}{side}{ladder}{halfladder}{index}"
        else:
            return f"M{unit}{face}{side}{ladder}{halfladder}{index}"

    return None
        
        

def is_valid_label(label: str, pattern: re.Pattern) -> bool:
    """
    Validate a label according to the required format.

    Parameters
    ----------
    label : str
        Label to validate.

    Returns
    -------
    bool
        True if the label matches the required format,
        otherwise False.
    """
    return bool(pattern.fullmatch(label))

def is_valid_module_name(label: str) -> bool:
    return (
        len(label) == 15
        and label[0] == "M"
        and label[1].isdigit()
        and label[2] in "UD"
        and label[3] in "LR"
        and label[4].isdigit()
        and label[5] in "TB"
        and label[6:12].isdigit()
        and label[13] in "ABCD"
        and label[14].isdigit()
    )

def patch_ladder_name(ladder_name: str, version:str = "STS3_5") -> str | None:
    """
        It transform the ladder name to a consistent naming for the STS3_5

        Raises: Value error under:
            - invalid ladder name 
            - invalid ladder name version
    """
    
    if not is_valid_label(ladder_name, LADDER_NAME_PATTERN):
        raise ValueError(f"Invalid ladder name: {ladder_name}")

    if version not in NAMING_VERSION:
        raise ValueError(f"Unknow ladder version: {version} not in {NAMING_VERSION}")

    if version == "STS8":
        return ladder_name
   
    if version == "STS3_5":
        unit_index = int(ladder_name[1])
        unit_face = ladder_name[2]
        
        if (unit_index == 3 and unit_face == "D") or unit_index > 3:
            new_index = unit_index + 1
            return ladder_name[0] + str(new_index) + ladder_name[2:]
        return ladder_name

def check_ladder_names(yaml_data) -> bool:
    for entry in yaml_data.get("types", []):
        name = list(entry.keys())[0]
        if name.startswith("L3D") or name.startswith("L4U"):
            raise ValueError(
                f"Invalid ladder name: {name}. Old unit 3 was broken down into 3U and 4D."
            )
    return True

def make_sts_address(
    unit: int,
    ladder: int,
    half_ladder: int,
    module: int,
    sensor: int = 0,
    side: int = 0,
    version: int = 1,
) -> int:
    # ECbmModuleId::kSts in C++
    STS_SYSTEM_ID = 2

    # bit limits from C++
    if not (0 <= unit < 64):
        raise ValueError("unit out of range")
    if not (0 <= ladder < 32):
        raise ValueError("ladder out of range")
    if not (0 <= half_ladder < 2):
        raise ValueError("half_ladder out of range")
    if not (0 <= module < 32):
        raise ValueError("module out of range")
    if not (0 <= sensor < 16):
        raise ValueError("sensor out of range")
    if not (0 <= side < 2):
        raise ValueError("side out of range")
    if not (0 <= version < 16):
        raise ValueError("version out of range")

    # creo que el problema era el orden de las operaciones, sin parentesis el shift tiene prioridad ante el and
    # ahora esta bien
    address = (
        STS_SYSTEM_ID
        | ((unit & 0x3F) << 4)
        | ((ladder & 0x1F) << 10)
        | ((half_ladder & 0x1) << 15)
        | ((module & 0x1F) << 16)
        | ((sensor & 0xF) << 21)
        | ((side & 0x1) << 25)
        | ((version & 0xF) << 28)
    )

    # keep lower 4 bytes
    return address & 0xFFFFFFFF

STS_NAME_TO_ADDRESS_DUMP = {}
def convert_to_cbm_sts_address(module_name: str, version: int = 1) -> int:
    """
    Parse STS module names

    Encoding rules:
      M<unit><D/U>L<ladder><B/U><module>

    - unit: digit after 'M'
    - side: D=1, U=0
    - ladder: digit after 'L'
    - half_ladder: first B/U after ladder (B=1, U=0)
    - module: digit immediately after that B/U
    - sensor: always 0 (index from legacy code)
    """

    # unit (single digit assumption from your example)
    if not module_name[1].isdigit():
        raise ValueError(f"Missing unit {module_name}")
    unit = int(module_name[1])

    # face
    if module_name[2] not in ("D", "U"):
        raise ValueError(f"Missing side (D/U) {module_name}")
    side = 1 if module_name[2] == "D" else 0

    # side
    if module_name[3] not in ("L", "R"):
        raise ValueError(f"Missing (L/R)  {module_name}")

    # ladder (single digit assumption from your example)
    if not module_name[4].isdigit():
        raise ValueError(f"Missing ladder {module_name}")
    ladder = int(module_name[4])

    # first B/U after ladder => half ladder
    if module_name[5] not in ("B", "T"):
        raise ValueError(f"Missing half-ladder (B/T) {module_name}")
    half_ladder = 1 if module_name[5] == "B" else 0

    # module index = digit right after that B/T
    if not module_name[6].isdigit():
        raise ValueError(f"Missing module index {module_name}")
    module = int(module_name[6])

    sensor = 0
    system = 2  # ECbmModuleId::kSts
    # print("converting ", module_name)
    # print(unit, ladder, half_ladder, module, sensor, side)

    # --- bit packing exactly like CbmStsAddress v1 ---
    address = make_sts_address(unit, ladder, half_ladder, module, sensor, side, version)

    STS_NAME_TO_ADDRESS_DUMP[
        f"{unit}\t{ladder}\t{half_ladder}\t{module}\t{sensor}\t{side}\t{version}"
    ] = address

    return address

    return address & 0xFFFFFFFF


def print_sts_bits(address: int) -> None:
    address &= 0xFFFFFFFF

    system = (address >> 0) & 0xF
    unit = (address >> 4) & 0x3F
    ladder = (address >> 10) & 0x1F
    half = (address >> 15) & 0x1
    module = (address >> 16) & 0x1F
    sensor = (address >> 21) & 0xF
    side = (address >> 25) & 0x1
    version = (address >> 28) & 0xF

    print(f"raw hex     : 0x{address:08X}")
    print(f"system      : {system}")
    print(f"unit        : {unit}")
    print(f"ladder      : {ladder}")
    print(f"half_ladder : {half}")
    print(f"module      : {module}")
    print(f"sensor      : {sensor}")
    print(f"side        : {side}")
    print(f"version     : {version}")


if __name__ == "__main__":
    print(hex(convert_to_cbm_sts_address("M5DL1B2001162B2")))

    print_sts_bits(convert_to_cbm_sts_address("M5DL1B2001162B2"))
