# EGV Parser released under MIT License.

from xml.etree.cElementTree import Element, ElementTree, SubElement


class EgvParser:

    def __init__(self):
        self.command = None
        self.distance = 0
        self.number_value = 0

    def parse(self, f):
        while True:
            byte = f.read(1)
            if byte is None or len(byte) == 0:
                break
            value = ord(byte)
            if ord('0') <= value <= ord('9'):
                self.append_digit(value - ord('0'))  # '0' = 0
                continue
            if ord('a') <= value <= ord('y'):
                self.append_distance(value - ord('a') + 1)  # 'a' = 1, not zero.
                continue
            if ord('A') <= value <= ord('Z') or value == ord('@'):
                if self.command is not None:
                    yield [self.command, self.distance, self.number_value]
                self.distance = 0
                self.number_value = 0
                self.command = byte
                continue
            if value == ord('z'):
                self.append_distance(255)
            if value == ord('|'):
                byte = f.read(1)
                if byte is None or len(byte) == 0:
                    break
                value = ord(byte)
                self.append_distance(26 + value - ord('a') + 1)  # '|a' = 27, not 26
        if self.command is not None:
            yield [self.command, self.distance, self.number_value]

    def append_digit(self, value):
        self.number_value *= 10
        self.number_value += value

    def append_distance(self, amount):
        self.distance += amount


MODE_E = 0b00000001  # Slow mode
MODE_V = 0b00000010  # Speed set
MODE_D = 0b00000100  # Laser On
MODE_X = 0b00001000  # Going -X
MODE_Y = 0b00010000  # Going -Y
MODE_F = 0b00100000  # Finishing.


class EgvInterpreter:
    def __init__(self):
        self.rail = 0
        self.current_x = 0
        self.current_y = 0
        self.draw_segments = []
        self.mode = 0
        self.number_value = 0
        self.distance_x = 0
        self.distance_y = 0
        self.raster_step = 0
        self.speed = None

    def commit_moves(self):
        if self.mode & MODE_X:
            next_x = self.current_x - self.distance_x
        else:
            next_x = self.current_x + self.distance_x
        if self.mode & MODE_Y:
            next_y = self.current_y - self.distance_y
        else:
            next_y = self.current_y + self.distance_y
        self.draw_segments.append([self.current_x, self.current_y, next_x, next_y, self.mode])
        self.current_x = next_x
        self.current_y = next_y
        self.distance_x = 0
        self.distance_y = 0

    def send(self, commands):
        cmd = commands[0]
        print(commands)
        if cmd is None:
            return
        elif cmd == b'T':  # move right
            self.distance_x += commands[1] + commands[2]
            if not self.mode & MODE_X:
                self.distance_y += self.raster_step
            self.mode |= MODE_X
            if self.mode & MODE_E:
                self.commit_moves()
        elif cmd == b'B':  # move left
            self.distance_x += commands[1] + commands[2]
            if self.mode & MODE_X:
                self.distance_y += self.raster_step
            self.mode &= ~MODE_X
            if self.mode & MODE_E:
                self.commit_moves()
        elif cmd == b'L':  # move top
            self.distance_y += commands[1] + commands[2]
            self.mode |= MODE_Y
            if self.mode & MODE_E:
                self.commit_moves()
        elif cmd == b'R':  # move bottom
            self.distance_y += commands[1] + commands[2]
            self.mode &= ~MODE_Y
            if self.mode & MODE_E:
                self.commit_moves()
        elif cmd == b'M':
            self.distance_x += commands[1] + commands[2]
            self.distance_y += commands[1] + commands[2]
            if self.mode & MODE_E:
                self.commit_moves()
        elif cmd == b'D':  # laser on
            self.mode |= MODE_D
        elif cmd == b'U':  # laser off
            self.mode &= ~MODE_D
        elif cmd == b'S':  # s command
            pass
        elif cmd == b'E':  # slow
            self.commit_moves()
            self.mode |= MODE_E
        elif cmd == b'P':  # pop
            self.commit_moves()
        elif cmd == b'I':  # interrupt
            self.mode &= ~MODE_F
        elif cmd == b'F':  # finish
            self.mode |= MODE_F
        elif cmd == b'C':  # cut
            self.raster_step = 0
        elif cmd == b'V':  # velocity
            self.speed = commands[2]
            self.mode |= MODE_V
        elif cmd == b'G':  # engrave
            self.raster_step = commands[2]
        elif cmd == b'N':  # next
            self.commit_moves()
            self.mode &= ~MODE_E
        elif cmd == b'@':  # reset
            self.mode &= ~MODE_E


def skip(file, byte, count):
    while count > 0:
        char = file.read(1)
        if char == byte:
            count -= 1


def skip_header(file):
    skip(file, b'\n', 3)
    skip(file, b'%', 5)


def get_bounds(values):
    min_x = float('inf')
    min_y = float('inf')
    max_x = -float('inf')
    max_y = -float('inf')
    for segments in values:
        if segments[4] & MODE_E:
            x0 = segments[0]
            y0 = segments[1]
            x1 = segments[2]
            y1 = segments[3]
            min_x = min(min_x, x0, x1)
            min_y = min(min_y, y0, y1)
            max_x = max(max_x, x0, x1)
            max_y = max(max_y, y0, y1)
    return min_x, min_y, max_x, max_y


def read(f):
    interpreter = EgvInterpreter()
    parser = EgvParser()
    with open(f, "rb") as file:
        skip_header(file)
        for command in parser.parse(file):
            interpreter.send(command)
    bounds = get_bounds(interpreter.draw_segments)
    for pos in interpreter.draw_segments:
        print(pos)
    tree = create_svg_dom(interpreter.draw_segments, bounds)
    tree.write(f + ".svg")


NAME_SVG = "svg"
ATTR_VERSION = "version"
VALUE_SVG_VERSION = "1.1"
ATTR_XMLNS = "xmlns"
VALUE_XMLNS = "http://www.w3.org/2000/svg"
ATTR_XMLNS_LINK = "xmlns:xlink"
VALUE_XLINK = "http://www.w3.org/1999/xlink"
ATTR_XMLNS_EV = "xmlns:ev"
VALUE_XMLNS_EV = "http://www.w3.org/2001/xml-events"
ATTR_WIDTH = "width"
ATTR_HEIGHT = "height"
ATTR_VIEWBOX = "viewBox"
NAME_PATH = "path"
ATTR_DATA = "d"
ATTR_FILL = "fill"
ATTR_STROKE = "stroke"
ATTR_STROKE_WIDTH = "stroke-width"
VALUE_NONE = "none"


def create_svg_dom(values, bounds):
    root = Element(NAME_SVG)
    root.set(ATTR_VERSION, VALUE_SVG_VERSION)
    root.set(ATTR_XMLNS, VALUE_XMLNS)
    root.set(ATTR_XMLNS_LINK, VALUE_XLINK)
    root.set(ATTR_XMLNS_EV, VALUE_XMLNS_EV)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    root.set(ATTR_WIDTH, str(width))
    root.set(ATTR_HEIGHT, str(height))
    viewbox = \
        str(bounds[0]) + " " + \
        str(bounds[1]) + " " + \
        str(width) + " " + \
        str(height)
    root.set(ATTR_VIEWBOX, viewbox)

    for segments in values:
        if segments[4] & MODE_E:
            path = SubElement(root, NAME_PATH)
            data = "M"
            x0 = segments[0]
            y0 = segments[1]
            x1 = segments[2]
            y1 = segments[3]
            data += " " + str(x0) + "," + str(y0)
            data += " " + str(x1) + "," + str(y1)
            path.set(ATTR_DATA, data)
            path.set(ATTR_FILL, VALUE_NONE)
            path.set(ATTR_STROKE, "#000")
            path.set(ATTR_STROKE_WIDTH, "1")
    return ElementTree(root)


# argv = sys.argv
# read(argv[1])
read("outfile1.EGV")
read("outfile2.EGV")
read("outfile3.EGV")
read("outfile4.EGV")
read("outfile5.EGV")
read("outfile6.EGV")
read("outfile7.EGV")
read("outfile8.EGV")
read("outfile9.EGV")

