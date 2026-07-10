from machine import Pin
import neopixel


class LedStrip:

    def __init__(self, pin: int, n_leds: int):

        self.n_leds = n_leds
        self.strip = neopixel.NeoPixel(Pin(pin), n_leds)

    def clear(self):

        for i in range(self.n_leds):
            self.strip[i] = (0, 0, 0)

        self.strip.write()

    def update(self, rgb_bytes):

        for i in range(self.n_leds):

            self.strip[i] = (
                rgb_bytes[3*i],
                rgb_bytes[3*i+1],
                rgb_bytes[3*i+2]
            )

        self.strip.write()