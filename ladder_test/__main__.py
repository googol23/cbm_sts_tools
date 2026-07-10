import argparse
import textwrap

from .led_controller import LedController
from ladder_layout import ladder_layout

def main(serial_port, setup, ladder_name):
    print(f"Serial port: {serial_port}\nSetup: {setup}\nLadder: {ladder_name}")

    # Map setup to MCU GPIO pin
    mcu_pin = {
        '0': 19,
        '1': 21
    }

    # Build layout
    layout = ladder_layout(ladder_name)
    print(layout)
    
    # Create LED controller simulation
    led_controller = LedController(
        serial_port=serial_port,
        n_leds=100,
        strip_length=1000,
        controler_pin=mcu_pin[setup]
    )
    

    # Example colors per sensor type
    # color_map = {
    #     SensorType(1): (255, 0, 0),      # red
    #     SensorType(2): (0, 255, 0),      # green
    #     SensorType(3): (0, 0, 255),      # blue
    #     SensorType(4): (255, 255, 0),    # yellow
    # }

    # Display simulated LEDs over ladder drawing
    led_controller.display(
        layout,
        # color_map=color_map,
        debug_img=True
    )

    
if __name__ == "__main__":

    description = textwrap.dedent("""
        Main interface to ladder test box LED strip controler
    """).expandtabs(4)

    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "--ladder_id",
        help="Unique ladder name",
        required=True)

    parser.add_argument(
        "--port",
        help="MCU serial port (e.g. COM3 or /dev/ttyUSB0)",
        required=True
    )
    
    parser.add_argument(
        "--setup",
        help="Test box setup id",
        required=True
    )    

    args = parser.parse_args()

    # try:
    main(args.port, args.setup, args.ladder_id)
    # except Exception as e:
    #     print(e)

    