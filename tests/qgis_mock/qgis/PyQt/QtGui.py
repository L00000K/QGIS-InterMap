class QColor:
    def __init__(self, r=0, g=0, b=0, a=255):
        self._r, self._g, self._b, self._a = r, g, b, a

    def red(self):
        return self._r

    def green(self):
        return self._g

    def blue(self):
        return self._b

    def alpha(self):
        return self._a

    def alphaF(self):
        return self._a / 255.0

    def name(self):
        return "#{:02x}{:02x}{:02x}".format(self._r, self._g, self._b)

    def isValid(self):
        return True


class QPainter:
    def __init__(self, *args):
        pass

    def end(self):
        pass


class QImage:
    def __init__(self, *args):
        pass
