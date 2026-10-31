"""Gera um .gpx sintético: 1 km plano, 3 km a subir 6 %, 2 km a descer."""
import math, sys

def gen(path):
    lat0, lon0 = 38.7223, -9.1393   # Lisboa
    pts, lat, lon, ele = [], lat0, lon0, 50.0
    step = 10.0  # metros entre pontos
    m_lat = 110540.0
    def seg(length, grade):
        nonlocal lat, ele
        for _ in range(int(length / step)):
            lat += step / m_lat
            ele += step * grade / 100.0
            pts.append((lat, lon, ele))
    seg(1000, 0.0)
    seg(3000, 6.0)
    seg(2000, -4.0)
    body = "\n".join(
        f'      <trkpt lat="{a:.7f}" lon="{b:.7f}"><ele>{c:.2f}</ele></trkpt>'
        for a, b, c in pts)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">\n'
           '  <trk><name>Serra de Teste</name><trkseg>\n' + body +
           '\n  </trkseg></trk>\n</gpx>\n')
    open(path, "w").write(xml)
    return len(pts)

if __name__ == "__main__":
    print(gen(sys.argv[1] if len(sys.argv) > 1 else "/tmp/t.gpx"), "pontos")
