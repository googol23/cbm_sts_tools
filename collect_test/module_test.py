from dataclasses import dataclass, asdict
from typing import Any, Callable, Self, ClassVar
import re

def parse_int(x: str) -> int:
    return int(x.strip())
    
def parse_float(x: str) -> float:
    return float(x.strip())
    
def parse_str(x: str) -> str:
    return x.strip()
    
def parse_int_list(x: str) -> list[int]:
    return [int(i) for i in x.strip().split()]

def parse_broken_channels(values: str) -> list[int]:
    return [ int(v.split("(")[0].strip()) for v in values.split(",") if len(v) != 0 ]

NUMBER_RE = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
VALUE_RE = re.compile(rf'''
^\s*
(?P<value>{NUMBER_RE})
(?:\s*\+/-\s*(?P<error>{NUMBER_RE}))?
(?:\s+(?P<unit>.+))?
\s*$
''', re.VERBOSE)

def parse_value_error_unit(x: str):
    m = VALUE_RE.match(x)
    if not m:
        raise ValueError(f"Bad format: {x}")

    return {
        "value": float(m.group("value")),
        "error": float(m.group("error")) if m.group("error") else None,
        "unit": m.group("unit")
    }
 

@dataclass
class ValueErrorUnit:
    value: float
    error: float | None
    unit: str | None
    
@dataclass
class ModuleTestResult:
    lab_id: str
    date: str
    operator_id: str
    module_id: str
    sensor_size: ValueErrorUnit
    mic_length: ValueErrorUnit
    estimated_cap: ValueErrorUnit
    no_db_metal_channels: int
    no_functional_asics_n_side: int
    active_asics_n_side: list[int]
    no_functional_asics_p_side: int
    active_asics_p_side: list[int]
    average_adc_enc_n_side: ValueErrorUnit
    average_adc_enc_p_side: ValueErrorUnit
    average_adc_enc_z_strips: ValueErrorUnit
    average_adc_thr_n_side: ValueErrorUnit
    average_adc_thr_p_side: ValueErrorUnit
    average_adc_gain_n_side: ValueErrorUnit
    average_adc_gain_p_side: ValueErrorUnit
    average_fast_enc_n_side: ValueErrorUnit
    average_fast_enc_p_side: ValueErrorUnit
    average_fast_thr_n_side: ValueErrorUnit
    average_fast_thr_p_side: ValueErrorUnit
    no_broken_channels_n_side: int
    list_broken_channels_n_side: list[int]
    no_broken_channels_p_side: int
    list_broken_channels_p_side: list[int]
    no_broken_channels_odd: int
    no_broken_channels_even: int

    # optional: keep full parsed dict if you still want flexibility
    raw: dict[str, Any] | None = None

    # Class-level dictionary (Created ONCE, high performance)
    PARAMETER_PARSERS: ClassVar[dict[str, Callable[[str], Any] | None]] = {
        "LAB_ID": parse_str,
        "DATE": parse_str,
        "OPERATOR_ID": parse_str,
        "MODULE_ID": parse_str,
        "SENSOR_SIZE": parse_value_error_unit,
        "MIC_LENGTH": parse_value_error_unit,
        "ESTIMATED CAP": parse_value_error_unit,
        "No._DB_METAL_CHANNELS": parse_int,
        "No._FUNCTIONAL_ASICs_N-side": parse_int,
        "ACTIVE_ASICs_N-side": parse_int_list,
        "No._FUNCTIONAL_ASICs_P-side": parse_int,
        "ACTIVE_ASICs_P-side": parse_int_list,
        "AVERAGE_ADC_ENC_N-side": parse_value_error_unit,
        "AVERAGE_ADC_ENC_P-side": parse_value_error_unit,
        "AVERAGE_ADC_ENC_Z-strips": parse_value_error_unit,
        "AVERAGE_ADC_THR_N-side": parse_value_error_unit,
        "AVERAGE_ADC_THR_P-side": parse_value_error_unit,
        "AVERAGE_ADC_GAIN_N-side": parse_value_error_unit,
        "AVERAGE_ADC_GAIN_P-side": parse_value_error_unit,
        "AVERAGE_FAST_ENC_N-side": parse_value_error_unit,
        "AVERAGE_FAST_ENC_P-side": parse_value_error_unit,
        "AVERAGE_FAST_THR_N-side": parse_value_error_unit,
        "AVERAGE_FAST_THR_P-side": parse_value_error_unit,
        "No._BROKEN_CHANNELS_N-side": parse_int,
        "LIST_BROKEN_CHANNELS_N-side": parse_broken_channels,
        "No._BROKEN_CHANNELS_P-side": parse_int,
        "LIST_BROKEN_CHANNELS_P-side": parse_broken_channels,
        "No._BROKEN_CHANNELS_ODD/EVEN": parse_int_list,
    
    }

    @classmethod
    def from_file(cls, file_path: str) -> Self:
        """Parses a file and returns an instantiated ModuleTestResult."""
        parsed_dict: dict[str, Any] = {}

        with open(file_path, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()

                if not line or ":" not in line:
                    continue

                par_name, values = line.split(":", 1)
                par_name = par_name.strip()
                values = values.strip()

                # Access the dict via the class namespace
                if par_name not in cls.PARAMETER_PARSERS:
                    continue

                parser = cls.PARAMETER_PARSERS[par_name]
                if parser is None:
                    continue

                try:
                    parsed_dict[par_name] = parser(values)
                except Exception as e:
                    raise ValueError(f"{e}, {par_name}, {file_path}") from e

        for required_par in cls.PARAMETER_PARSERS.keys():
            if required_par not in parsed_dict:
                raise KeyError(f"Parameter {required_par} failed to parse in file {file_path}")

        # Ensure defaults exist for missing keys to prevent KeyError crashes
        # Casting count variables to integers directly during mapping
        return cls(
            lab_id=parsed_dict.get("LAB_ID", ""),
            date=parsed_dict.get("DATE", ""),
            operator_id=parsed_dict.get("OPERATOR_ID", ""),
            module_id=parsed_dict.get("MODULE_ID", ""),
            sensor_size=parsed_dict["SENSOR_SIZE"],
            mic_length=parsed_dict["MIC_LENGTH"],
            estimated_cap=parsed_dict["ESTIMATED CAP"],
            no_db_metal_channels=int(parsed_dict.get("No._DB_METAL_CHANNELS", 0)),
            no_functional_asics_n_side=int(parsed_dict.get("No._FUNCTIONAL_ASICs_N-side", 0)),
            active_asics_n_side=parsed_dict.get("ACTIVE_ASICs_N-side", []),
            no_functional_asics_p_side=int(parsed_dict.get("No._FUNCTIONAL_ASICs_P-side", 0)),
            active_asics_p_side=parsed_dict.get("ACTIVE_ASICs_P-side", []),
            average_adc_enc_n_side=parsed_dict["AVERAGE_ADC_ENC_N-side"],
            average_adc_enc_p_side=parsed_dict["AVERAGE_ADC_ENC_P-side"],
            average_adc_enc_z_strips=parsed_dict["AVERAGE_ADC_ENC_Z-strips"],
            average_adc_thr_n_side=parsed_dict["AVERAGE_ADC_THR_N-side"],
            average_adc_thr_p_side=parsed_dict["AVERAGE_ADC_THR_P-side"],
            average_adc_gain_n_side=parsed_dict["AVERAGE_ADC_GAIN_N-side"],
            average_adc_gain_p_side=parsed_dict["AVERAGE_ADC_GAIN_P-side"],
            average_fast_enc_n_side=parsed_dict["AVERAGE_FAST_ENC_N-side"],
            average_fast_enc_p_side=parsed_dict["AVERAGE_FAST_ENC_P-side"],
            average_fast_thr_n_side=parsed_dict["AVERAGE_FAST_THR_N-side"],
            average_fast_thr_p_side=parsed_dict["AVERAGE_FAST_THR_P-side"],
            no_broken_channels_n_side=int(parsed_dict.get("No._BROKEN_CHANNELS_N-side", 0)),
            list_broken_channels_n_side=parsed_dict.get("LIST_BROKEN_CHANNELS_N-side", []),
            no_broken_channels_p_side=int(parsed_dict.get("No._BROKEN_CHANNELS_P-side", 0)),
            list_broken_channels_p_side=parsed_dict.get("LIST_BROKEN_CHANNELS_P-side", []),
            no_broken_channels_odd=parsed_dict.get("ODD", 0), # TODO: fix parsers
            no_broken_channels_even=parsed_dict.get("EVEN", 0), # TODO: fix parsers
            raw=parsed_dict,
        )


if __name__ == "__main__":
    file = "test_result/L0DL000150/M0DL0B0001500B5/pscan_files/module_test_M0DL0B0001500B5.txt"
    module_test_result = ModuleTestResult.from_file(file)
    for name, value in asdict(module_test_result).items():
        print(f"{name}: {value}")