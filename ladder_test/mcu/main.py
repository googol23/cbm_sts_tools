from led_strip import LedStrip
from serial_protocol import SerialProtocol

NUM_LEDS = 100

strip = LedStrip(
    pin=21,
    n_leds=NUM_LEDS
)

protocol = SerialProtocol(NUM_LEDS)

strip.clear()

while True:

    packet = protocol.receive()

    if packet is None:
        continue

    pin, payload = packet

    strip.update(payload)