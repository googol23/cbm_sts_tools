from dataclasses import dataclass

SENSOR_OVERLAP_MM: float = 4.2  # mm
SENSOR_OVERLAP_CM: float = 0.1 * SENSOR_OVERLAP_MM

STS_SENSOR_SIZE: dict[int, tuple[float, float]] = {
    0: (62, 22),
    1: (62, 22),
    2: (62, 42),
    3: (62, 62),
    4: (62, 124),
}

COLOR_BY_SIZE = {
    22 : 'red',
    42 : 'green',
    62 : 'cyan',
    124 : 'blue'
}

@dataclass(frozen=True)
class SensorType:
    """
    It holds the related information to a sensor type
    """
    id: int
    
    def size_xy(self)->tuple[float,float]:
        return STS_SENSOR_SIZE[int(self.id)]

    def __str__(self):
        """ This string is structure correspong to the CBMROOT enum name and shall not be modified """
        return f"k{self.size_xy()[0]}_{self.size_xy()[0]}"

if __name__ == "__main__":
    print(SensorType(3).size_xy())