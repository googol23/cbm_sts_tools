import sys

class SerialProtocol:

    START_BYTE = 0xAA

    def __init__(self, n_leds):

        self.payload_size = n_leds * 3

    def receive(self):

        # Wait for start byte
        while True:

            b = sys.stdin.buffer.read(1)

            if not b:
                return None

            if b[0] == self.START_BYTE:
                break

        # Read pin
        pin = sys.stdin.buffer.read(1)[0]

        # Read LED payload
        payload = sys.stdin.buffer.read(self.payload_size)

        if len(payload) != self.payload_size:
            return None

        # Read checksum
        checksum = sys.stdin.buffer.read(1)

        if len(checksum) != 1:
            return None

        checksum = checksum[0]

        calc = self.START_BYTE + pin

        for b in payload:
            calc += b

        calc &= 0xFF

        if calc != checksum:
            print("Checksum error")
            return None

        return pin, payload