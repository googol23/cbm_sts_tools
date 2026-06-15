import numpy as np
from dataclasses import dataclass

import yaml

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

import psycopg2


from db.cf_support import CF_SUPPORT_TYPE
from db.sensor_type import SensorType, SENSOR_OVERLAP_MM, COLOR_BY_SIZE
from db.db_api import get_conn, get_latest_modules_for_ladder, list_ladder_names

from utils.sts_naming import is_valid_module_name


@dataclass
class LadderLayout:
    """
    It holds the sensor types sorted bottom to top

    Internally uses all dimensions in mm
    """
    sensor_types: list[SensorType]
    cutout_size: float = 0
    length:float = 0

    @property
    def n_sensors(self)->int:
        return len(self.sensor_types)
    
    @property
    def ladder_size_xy(self)->tuple[float, float]:
        ladder_size = np.sum(self.sensors_size_xy(), axis=0)
        return ladder_size[0], ladder_size[1] + self.cutout_size
        
    def sensors_size_xy(self)->np.ndarray:
        return np.array([s.size_xy() for s in self.sensor_types], dtype=np.float32)
    
    def sensor_positions(self) -> np.ndarray:
        """
        It calculate the nominal sensor positions based on nominal sensor overlap along y-axis.
        """
        sizes_t = self.sensors_size_xy()[int(0.5*self.n_sensors):]
        
        positions_y =  np.empty(shape=(self.n_sensors), dtype=np.float32)
        offset_y = 0.5 * self.cutout_size + 0.5*SENSOR_OVERLAP_MM if self.cutout_size > 0.2 else 0

        for idx in range(int(0.5*self.n_sensors)):
            y = offset_y + 0.5 * (sizes_t[idx][1] - SENSOR_OVERLAP_MM)
            offset_y = y + 0.5 * (sizes_t[idx][1] - SENSOR_OVERLAP_MM)

            positions_y[idx] = y
            positions_y[int(0.5*self.n_sensors) + idx] = -y
            
        positions_y.sort()
        return positions_y

    def sensor_bbox(self) -> np.ndarray:
        sizes = self.sensors_size_xy()
        positions_y = self.sensor_positions()
    
        bboxes = np.empty((self.n_sensors, 4), dtype=np.float32)
    
        for i, (y, (w, h)) in enumerate(zip(positions_y, sizes)):
            x_min = -0.5 * w
            x_max =  0.5 * w
            y_min = y - 0.5 * h
            y_max = y + 0.5 * h
    
            bboxes[i] = [x_min, x_max, y_min, y_max]
    
        return bboxes
        
    def draw(self) -> None:
        """
        Draw the ladder layout.
        """
        # Constants
        PLOT_DPI = 600
                    
        aspect_ratio = self.ladder_size_xy[1] / self.ladder_size_xy[0]
        
        # Create figure with proper dimensions
        fig_width_pxl = 3000  # Base width in inches
        fig_height_pxl = fig_width_pxl / aspect_ratio
        fig = plt.figure(figsize=(fig_width_pxl / PLOT_DPI, fig_height_pxl / PLOT_DPI), dpi=PLOT_DPI)
        plt.rcParams['axes.axisbelow'] = True

        # Create axes with proper dimensions
        ax = fig.add_subplot(111)
        ax.set_aspect('equal', 'box')
        ax.set_xlim(-2.5*self.ladder_size_xy[0], 2.5*self.ladder_size_xy[0])
        ax.set_ylim(-1.5*self.ladder_size_xy[1], 1.5*self.ladder_size_xy[1])
        ax.grid(True, which='both', color='gray', linestyle='--', linewidth=0.5, zorder=0)
        
        for spine in ax.spines.values():
            spine.set_linewidth(0.0001 * fig_height_pxl)
        
        ax.tick_params(
            direction='out',      # ticks point inward
            length=6, width=1,   # optional tick size
            top=True,         # ticks on top
            right=True,       # ticks on right
            labelbottom=True,    # x-axis labels on bottom
            labeltop=True,      # x-axis labels on top
            labelleft=True,      # y-axis labels on left
            labelright=True,    # y-axis labels on right
            # pad=30              # negative padding moves labels inward
        )
                
        sizes = self.sensors_size_xy()
        positions_y = self.sensor_positions()

        for y, (w, h) in zip(positions_y, sizes):
            rect = Rectangle(
                (0 - 0.5 * w, y - 0.5 * h),
                w,
                h,
                fill=True,
                edgecolor='black',
                facecolor=COLOR_BY_SIZE[abs(h)],
                alpha=0.3
            )
            ax.add_patch(rect)
        
        ax.set_aspect('equal')
        ax.autoscale()

    def to_dict(self):
        return {
        "length": 0.1*self.length,
        "firstSensorOffsetY": 0.1*(self.cutout_size if self.cutout_size else 0.5*SENSOR_OVERLAP_MM),
        "layout" : FlowList([f"{s}" for s in self.sensor_types[:len(self.sensor_types) // 2]])
        }

    def __str__(self):
        return f"""\
            Number of modules: {self.n_sensors}
            {self.sensor_types}
            length: {self.length}
            cut-out size: {self.cutout_size}\
        """

    
        
def sort_tb(values: list[str]) -> list[str]:
    def key(s: str):
        letter = s[5]
        digit = int(s[6])
        # print(letter, digit)
        if letter == "B":
            return (0, -digit)   # B first, descending digit
        else:  # T
            return (1, digit)    # T after, ascending digit

    return sorted(values, key=key)
        
def ladder_layout(ladder_name: str, conn: psycopg2.extensions.connection | None = None) -> LadderLayout:
    if conn is None:
        conn = get_conn()

    modules = get_latest_modules_for_ladder(ladder_name, conn)
    # Ensure sorting of modules from bottom to top
    modules = sort_tb(modules)
    
    if len(modules) % 2 != 0:
        raise ValueError(f"Ladder {ladder_name} module list is not symmetric")

    sensors: list[SensorType] = []

    with conn.cursor() as cur:
        for m in modules:
            if not is_valid_module_name(m) < 6:
                raise ValueError(f"Invalid module name: {m}")
            
            cur.execute("""
                SELECT sensor_name
                FROM public.sts_module
                WHERE name = %s;
            """, (m,))
            row = cur.fetchone()

            if not row:
                raise ValueError(f"Missing sensor_name for module {m}")
            
            try:
                sensor_type = int(row["sensor_name"][-1])
                sensors.append(SensorType(sensor_type))
                # print(m, sensor_type)
            except Exception:
                print("Failed while getting sensor size")

    
    cf_support_type = int(ladder_name[-2:])
    cutout_size = CF_SUPPORT_TYPE[cf_support_type][4] # File untis are in MM
    length = CF_SUPPORT_TYPE[cf_support_type][5] # File untis are in MM
    
    return LadderLayout(sensors, cutout_size, length)

# ------------------------------------------------------------------
# YAML dumping
# ------------------------------------------------------------------
class FlowList(list):
    """ Marker type for flow-style lists """

def flow_list_representer(dumper, data):
    return dumper.represent_sequence(
        "tag:yaml.org,2002:seq",
        data,
        flow_style=True,
    )

def float_representer(dumper, value):
    return dumper.represent_scalar(
        "tag:yaml.org,2002:float",
        f"{value:.2f}"
    )

yaml.add_representer(float, float_representer)
yaml.add_representer(FlowList, flow_list_representer)

def generate_ladders_layout() -> dict[str, list[str]]:
    """
    It produces a dict for later YAML dump
    key: ladder name
    value: list str: str is the literal representation of the c++ enum class for sensor size:
        e.g k62_22 is a sensor of 62mm(dx) x 22mm(dy)
    """
    layouts: dict[str, list[str]] = {}

    conn = get_conn()
    ladder_list = list_ladder_names(conn)


    yaml_data = {
        "types": [
            {
                ladder_name: ladder_layout(ladder_name).to_dict()
            }
            for ladder_name in ladder_list
        ]
    }

    yaml_data["types"].sort(key=lambda d: list(d.keys())[0])

    with open("test.yaml", "w") as f:
        yaml.dump(yaml_data, f, sort_keys=False, default_flow_style=False)
    
    
    return layouts
        
if __name__ == "__main__":
    generate_ladders_layout()
    