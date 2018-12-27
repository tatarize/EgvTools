import struct
import zlib
from math import ceil


class PngRaster:
    def __init__(self, width, height, bit_depth=2, color_type=0):
        self.color_type = color_type
        self.bit_depth = bit_depth
        self.samples_per_pixel = 1
        self.width = width
        self.height = height
        self.samples_per_pixel = self.get_sample_count(color_type)
        self.stride = self.get_stride(self.samples_per_pixel, self.bit_depth, self.width)
        self.buf = []
        for i in range(height):
            line = bytearray(b'\x00' + b'\xFF' * self.stride)
            self.buf.append(line)

    @staticmethod
    def get_stride(sample_count, bit_depth, width):
        return int(ceil(bit_depth * sample_count * width / 8.0))

    @staticmethod
    def get_sample_count(color_type):
        if color_type == 0:
            return 1
        elif color_type == 2:
            return 3
        elif color_type == 3:
            return 1
        elif color_type == 4:
            return 2
        elif color_type == 6:
            return 4
        else:
            return 1

    def save_png(self, filename):
        with open(filename, "wb") as f:
            f.write(self.get_png_bytes())

    def get_png_bytes(self):
        buf = self.buf
        width = self.width
        height = self.height
        raw_data = b"".join(buf[i] for i in range(0, height))

        def png_pack(png_tag, data):
            chunk_head = png_tag + data
            return struct.pack("!I", len(data)) + chunk_head + struct.pack("!I", 0xFFFFFFFF & zlib.crc32(chunk_head))

        return b"".join([
            b'\x89PNG\r\n\x1a\n',
            png_pack(b'IHDR', struct.pack("!2I5B", width, height, self.bit_depth, self.color_type, 0, 0, 0)),
            png_pack(b'IDAT', zlib.compress(raw_data, 9)),
            png_pack(b'IEND', b'')])

    @staticmethod
    def read_png_chunks(file):
        while True:
            length_bytes = file.read(4)
            if len(length_bytes) == 0:
                break
            length = struct.unpack(">I", length_bytes)[0]
            byte = file.read(4)
            signature = byte.decode('utf8')
            data = file.read(length)
            crc = file.read(4)
            if len(signature) == 0:
                break
            yield signature, data
            if signature == 'IEND':
                break

    def read_png_file(self, file):
        with open(file, "rb") as f:
            self.read_png_stream(f)

    def read_png_stream(self, file):
        if file.read(8) != b'\x89PNG\r\n\x1a\n':
            return  # Not a png file.
        zlib_data = b''
        for chunk in self.read_png_chunks(file):
            signature = chunk[0]
            data = chunk[1]
            if signature == 'IHDR':
                self.width = struct.unpack(">I", data[0:4])[0]
                self.height = struct.unpack(">I", data[4:8])[0]
                self.bit_depth = data[8]
                self.color_type = data[9]
            elif signature == 'IDAT':
                zlib_data += data
            elif signature == 'IEND':
                break
        png_data = zlib.decompress(zlib_data)
        self.stride = self.get_stride(self.samples_per_pixel, self.bit_depth, self.width)
        self.samples_per_pixel = self.get_sample_count(self.color_type)
        self.buf = [
            bytearray(png_data[line:line + self.stride])
            for line in range(0, len(png_data), self.stride)
        ]

    def draw_line(self, x0, y0, x1, y1, color=0):
        dy = y1 - y0  # BRESENHAM LINE DRAW ALGORITHM
        dx = x1 - x0
        if dy < 0:
            dy = -dy
            step_y = -1
        else:
            step_y = 1
        if dx < 0:
            dx = -dx
            step_x = -1
        else:
            step_x = 1
        if dx > dy:
            dy <<= 1  # dy is now 2*dy
            dx <<= 1
            fraction = dy - (dx >> 1)  # same as 2*dy - dx
            self.plot(x0, y0, color)

            while x0 != x1:
                if fraction >= 0:
                    y0 += step_y
                    fraction -= dx  # same as fraction -= 2*dx
                x0 += step_x
                fraction += dy  # same as fraction += 2*dy
                self.plot(x0, y0, color)
        else:
            dy <<= 1  # dy is now 2*dy
            dx <<= 1  # dx is now 2*dx
            fraction = dx - (dy >> 1)
            self.plot(x0, y0, color)
            while y0 != y1:
                if fraction >= 0:
                    x0 += step_x
                    fraction -= dy
                y0 += step_y
                fraction += dx
                self.plot(x0, y0, color)

    def get_pixel(self, x, y):
        scanline = self.buf[y]
        pixel_length_in_bits = self.samples_per_pixel * self.bit_depth

        start_pos_in_bits = x * pixel_length_in_bits
        end_pos_in_bits = start_pos_in_bits + pixel_length_in_bits - 1
        start_pos_in_bytes = int(start_pos_in_bits / 8) + 1  # byte 0 is interlacing
        end_pos_in_bytes = int(end_pos_in_bits / 8) + 1  # byte 0 is interlacing

        section = scanline[start_pos_in_bytes:end_pos_in_bytes + 1]
        value = int.from_bytes(section, byteorder='big', signed=False)
        return value

    def set_pixel(self, x, y, sample):
        scanline = self.buf[y]
        pixel_length_in_bits = self.samples_per_pixel * self.bit_depth

        start_pos_in_bits = x * pixel_length_in_bits
        end_pos_in_bits = start_pos_in_bits + pixel_length_in_bits - 1
        start_pos_in_bytes = int(start_pos_in_bits / 8) + 1  # byte 0 is interlacing
        end_pos_in_bytes = int(end_pos_in_bits / 8) + 1  # byte 0 is interlacing

        section = scanline[start_pos_in_bytes:end_pos_in_bytes + 1]
        value = int.from_bytes(section, byteorder='big', signed=False)

        unused_bits_right_of_sample = (end_pos_in_bits + 1) % 8
        mask_sample_bits = (1 << pixel_length_in_bits) - 1

        value &= ~(mask_sample_bits << unused_bits_right_of_sample)
        value |= (sample & mask_sample_bits) << unused_bits_right_of_sample
        for pos in range(end_pos_in_bytes, start_pos_in_bytes - 1, -1):
            scanline[pos] = value & 0xff
            value >>= 8

    def plot(self, x, y, color):
        if not 0 <= x < self.width:
            return
        if not 0 <= y < self.height:
            return
        self.set_pixel(x, y, color)
        # scanline = self.stride * y
        # pos_byte = int(x / 8)
        # pos_bit = int(x % 8)
        # pos = scanline + pos_byte
        # byte = int(self.buf[pos])
        # byte &= (~(1 << (7 - pos_bit)))
        # self.buf[pos] = byte
