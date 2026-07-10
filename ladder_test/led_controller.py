import serial

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from db.sensor_type import SensorType
from ladder_layout import LadderLayout


class LedController:
    def __init__(self, serial_port, n_leds: int, strip_length:float, controler_pin: int | None = None):
        print("Building controler object")
        
        self.serial = None
        try:
            self.serial = serial.Serial(
                port=serial_port,
                baudrate=115200,
                timeout=1
            )
        except Exception as e:
            print(e)
        
        self.n_leds = n_leds
        self.strip_length = strip_length
        self.controler_pin = controler_pin

        # WS2812B buffer
        self.leds = np.zeros((n_leds, 3), dtype=np.uint8)


    def clear(self):
        self.leds[:] = (0, 0, 0)

    def send(self):
        MSG_START = 0xAA
        print(
            f"Sending layout to device at {self.serial} "
            f"for pin {self.controler_pin}"
        )
    
        led_data = self.leds.tobytes()
    
        packet = bytearray()
    
        # Header
        packet.append(MSG_START)
        packet.append(self.controler_pin)
    
        # LED payload
        packet.extend(led_data)
    
        # Optional checksum
        checksum = sum(packet) & 0xFF
        packet.append(checksum)

        # Inspect packet
        print(f"Packet length: {len(packet)} bytes")
        print("TX:", packet.hex(" "))
    
        if self.serial is None:
            return
                
        self.serial.write(packet)


    def display(self, layout: LadderLayout, color_map: dict | None = None, debug_img: bool = False):
        self.clear()

        if color_map is None:
            color_cycle = [
                    (255, 0, 0),    # red
                    (0, 0, 255),    # blue
                    (0, 255, 0),    # green
                ]
        else:
            color_cycle = None

        # Map sensors to LEDs
        for sensor_idx, (sensor, bbox) in enumerate(zip(layout.sensor_types, layout.sensor_bbox())):
            sensor_y_min = bbox[2]
            sensor_y_max = bbox[3]

            # print(sensor_idx, bbox, sensor_y_min, sensor_y_max)            
            if color_map is not None:
                color = color_map.get(
                    sensor,
                    (255, 255, 255)
                )
            else:
                color = [
                    (255, 0, 0),    # red
                    (0, 0, 255),    # blue
                    (0, 255, 0),    # green
                ][sensor_idx % 3]
        
            for i_led in range(self.n_leds):
                y_led = float(self.strip_length / self.n_leds * i_led) - 0.5*layout.ladder_size_xy[1] - 0.5# + offset # (Correction for strip edge offset of first led) 
                
                if sensor_y_min < y_led < sensor_y_max:
                    self.leds[i_led] = color


        if debug_img:
            self.debug_plot(layout)

        self.send()


    def debug_plot(self, layout):
        fig = layout.draw()
        ax = fig.axes[0]

        total_height = layout.ladder_size_xy[1]

        led_width = layout.ladder_size_xy[0] * 0.01
        led_height = self.strip_length / self.n_leds
        
        for i, rgb in enumerate(self.leds):
        
            color = rgb / 255.0
        
            # LED center position in ladder coordinates
            y_center = (
                -0.5 * total_height
                + (i + 0.5) * led_height
            )
        
            led = Rectangle(
                (
                    0.08 * layout.ladder_size_xy[0],
                    y_center - 0.35 * led_height
                ),
                led_width,
                led_height,
                facecolor=color,
                edgecolor="black",
                linewidth=0.2
            )
        
            ax.add_patch(led)


        fig.canvas.draw()
        plt.savefig(f"ladder_test/led_panel_test.png")