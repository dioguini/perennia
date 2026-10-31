#!/usr/bin/env python3
"""Perennia — ponto de entrada.

    python main.py                 # abre a aplicação
    python main.py --fullscreen
    python main.py --data-dir ./dados
    python main.py --self-test     # verifica o núcleo sem abrir janela
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from velo import paths  # noqa: E402


def self_test() -> int:
    """Confirma que o núcleo funciona nesta máquina, sem abrir janela."""
    import tempfile, time
    from velo.core import climbs, fit, gpx, physics
    from velo.core.db import Athlete, Database
    from velo.core.ride import RideEngine
    from velo.io.hub import SensorHub
    from velo.io.sim import SimulatedTrainer

    sample_gpx = paths.resource("tests", "teste.gpx")
    if not sample_gpx.exists():
        print("falta tests/teste.gpx"); return 1

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "perennia.db")
        db.save_athlete(Athlete(name="Autoteste", weight_kg=72.0, ftp_w=250, lthr=165))
        name, points = gpx.import_gpx(sample_gpx)
        found = climbs.detect(points)
        route_id = db.insert_route(name, points, found, sample_gpx.name)
        print(f"  rota: {name} — {points[-1].dist_m/1000:.2f} km, {len(found)} subida(s)")

        trainer = SimulatedTrainer(base_power=210)
        hub = SensorHub(); hub.add_source(trainer, role="trainer", is_trainer=True)
        engine = RideEngine(db, db.athlete(), route_id=route_id,
                            points=db.route_points(route_id),
                            climbs=db.climbs(route_id), sensors=hub, trainer=hub,
                            rides_dir=Path(tmp) / "rides")
        steps = 0
        while steps < 40000 and not engine.route_finished:
            hub.tick(0.25); engine.update(0.25); engine.drain_events(); steps += 1
        result = engine.finish()
        s = result["summary"]
        print(f"  sessão: {s.distance_m/1000:.2f} km em {s.elapsed_s/60:.1f} min, "
              f"{s.avg_power_w:.0f} W médios, TSS {s.tss:.0f}")
        info = fit.verify(result["fit_path"])
        print(f"  .fit: {Path(result['fit_path']).name} — {info['bytes']} bytes, "
              f"{info['messages'].get(20,0)} registos — CRC ok")
        db.close()
    print("núcleo OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Perennia")
    parser.add_argument("--data-dir", default=None,
                        help="pasta da base de dados e dos .fit")
    parser.add_argument("--fullscreen", action="store_true", default=None,
                        help="ecrã inteiro (senão, usa a última escolha)")
    parser.add_argument("--window", action="store_true",
                        help="em janela, mesmo que da última vez fosse ecrã inteiro")
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--height", type=int, default=None)
    parser.add_argument("--self-test", action="store_true",
                        help="testa o núcleo e sai, sem abrir janela")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    try:
        import pyglet  # noqa: F401
    except ImportError:
        print("A biblioteca pyglet não está instalada.\n"
              "Instala as dependências com:\n"
              "    python -m pip install -r requirements.txt\n"
              "Para verificar o núcleo sem interface: python main.py --self-test",
              file=sys.stderr)
        return 2

    from velo.ui.app import App, _default_data_dir
    try:
        fullscreen = False if args.window else args.fullscreen
        app = App(data_dir=args.data_dir, width=args.width, height=args.height,
                  fullscreen=fullscreen)
        try:
            app.run()
        except BaseException:
            # Erro inesperado (ou Ctrl+C): a sessão em curso não se termina.
            # Fica gravada e, ao abrir de novo, a aplicação pergunta se retoma.
            app.shutdown(crashed=True)
            raise
        app.shutdown()
    except Exception:
        report_crash(Path(args.data_dir) if args.data_dir else _default_data_dir())
        return 1
    return 0


def report_crash(data_dir: Path) -> None:
    """No executável não há consola: o erro vai para um ficheiro e aparece
    numa caixa de diálogo, para quem usa a aplicação o poder enviar."""
    import traceback
    text = traceback.format_exc()
    log = data_dir / "perennia-erro.log"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        log.write_text(text, encoding="utf-8")
    except OSError:
        log = None
    print(text, file=sys.stderr)
    if paths.frozen() and sys.platform == "win32":
        try:
            import ctypes
            where = f"\n\nO erro foi gravado em:\n{log}" if log else ""
            ctypes.windll.user32.MessageBoxW(
                None, "A Perennia fechou por causa de um erro." + where
                + "\n\nEnvia esse ficheiro a quem te passou a aplicação.",
                "Perennia", 0x10)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
