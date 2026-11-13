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

from perennia import paths  # noqa: E402


def self_test() -> int:
    """Confirma que o núcleo funciona nesta máquina, sem abrir janela."""
    import tempfile, time
    from perennia.core import climbs, fit, gpx, physics
    from perennia.core.db import Athlete, Database
    from perennia.core.ride import RideEngine
    from perennia.io.hub import SensorHub
    from perennia.io.sim import SimulatedTrainer

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
    parser.add_argument("--backup", nargs="?", const="", default=None, metavar="DESTINO",
                        help="faz um backup e sai (pasta ou ficheiro .zip; por omissão, "
                             "a pasta backups dos dados)")
    parser.add_argument("--restore", default=None, metavar="BACKUP.zip",
                        help="repõe um backup e sai (antes guarda o que tens agora)")
    parser.add_argument("--componentes", default=None,
                        help="só estas componentes, separadas por vírgulas (ex.: rotas,sessoes)")
    parser.add_argument("--modo", default="substituir", choices=("substituir", "juntar"),
                        help="na reposição: substituir (cópia exata) ou juntar (acrescenta)")
    parser.add_argument("--credenciais", action="store_true",
                        help="no backup, incluir as credenciais (Strava)")
    parser.add_argument("--importar", nargs=2, default=None, metavar=("TIPO", "FICHEIRO"),
                        help="importa um ficheiro e sai: hrv4training (.csv), analises "
                             "(.csv/.xlsx), trainingpeaks (.csv de atividades) ou atividade "
                             "(um .fit ou .tcx, guardado no desporto respetivo) ou csv (artigos, "
                             "exercícios, grupos musculares… — descobre o conjunto pelo "
                             "cabeçalho) ou saude (o .csv do diário de saúde por data)")
    parser.add_argument("--csv-modelo", default=None, metavar="CONJUNTO",
                        help="grava o modelo .csv de um conjunto (artigos, exercicios, grupos, "
                             "disciplinas, testes, material) e sai")
    parser.add_argument("--csv-exportar", default=None, metavar="CONJUNTO",
                        help="exporta um conjunto para .csv e sai")
    parser.add_argument("--adhoc-exportar", default=None, metavar="FONTE",
                        help="exporta para .csv uma fonte da Análise AdHoc e sai (sessions, "
                             "sets, daily, labs, tests ou bp); com --vista usa os campos e filtros "
                             "dessa vista guardada")
    parser.add_argument("--vista", default=None,
                        help="com --adhoc-exportar: o nome de uma vista guardada")
    parser.add_argument("--nome", default=None,
                        help="com --adhoc-exportar: o nome do ficheiro (sem pastas)")
    parser.add_argument("--separador", default=None,
                        help="com --adhoc-exportar: ; , | ou tab (por omissão, o das Definições)")
    parser.add_argument("--decimal", default=None,
                        help="com --adhoc-exportar: . ou , (por omissão, o das Definições)")
    parser.add_argument("--testar-hr-ant", nargs="?", const=30.0, default=None, type=float,
                        metavar="SEGUNDOS",
                        help="testa só a FC por ANT+ (cinta ou relógio a transmitir) e sai: abre "
                             "um único canal e escreve o que chega, ao segundo")
    parser.add_argument("--destino", default=None,
                        help="pasta onde gravar os .csv (por omissão, Transferências)")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if args.backup is not None or args.restore:
        return backup_cli(args)
    if args.testar_hr_ant is not None:
        from perennia.io import ant
        res = ant.hr_test(args.testar_hr_ant)
        return 0 if res["valid"] else 1
    if args.importar:
        return import_cli(args)
    if args.csv_modelo or args.csv_exportar:
        return csv_cli(args)
    if args.adhoc_exportar:
        return adhoc_cli(args)

    try:
        import pyglet  # noqa: F401
    except ImportError:
        print("A biblioteca pyglet não está instalada.\n"
              "Instala as dependências com:\n"
              "    python -m pip install -r requirements.txt\n"
              "Para verificar o núcleo sem interface: python main.py --self-test",
              file=sys.stderr)
        return 2

    from perennia.ui.app import App, _default_data_dir
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


def csv_cli(args) -> int:
    """O modelo ou a exportação de um conjunto em .csv, sem abrir a janela."""
    from perennia.core import csv_sync
    from perennia.core.db import Database
    from perennia.core.workout_download import downloads_dir
    from perennia.datadir import data_dir_for, database_path
    key = args.csv_modelo or args.csv_exportar
    if key == "saude":                       # os campos do diário de saúde, por data
        from perennia.core import health_csv
        db = Database(database_path(data_dir_for(args.data_dir)))
        try:
            print(health_csv.write(db, args.destino or downloads_dir(),
                                   what="template" if args.csv_modelo else "export"))
        finally:
            db.close()
        return 0
    if key not in csv_sync.DATASETS:
        print("Conjunto desconhecido: " + key + "\nExistem: " + ", ".join(csv_sync.DATASETS)
              + ", saude", file=sys.stderr)
        return 2
    db = Database(database_path(data_dir_for(args.data_dir)))
    try:
        print(csv_sync.write(db, key, args.destino or downloads_dir(),
                             what="template" if args.csv_modelo else "export"))
    finally:
        db.close()
    return 0


def adhoc_cli(args) -> int:
    """O .csv da Análise AdHoc pela linha de comandos, sem abrir a janela."""
    from perennia.core import adhoc
    from perennia.core.db import Database
    from perennia.datadir import data_dir_for, database_path
    data_dir = data_dir_for(args.data_dir)
    sep = "\t" if (args.separador or "").lower() in ("tab", "\\t") else args.separador
    db = Database(database_path(data_dir))
    try:
        path, n = adhoc.cli_export(db, data_dir, args.adhoc_exportar, args.destino, args.vista,
                                   args.nome, sep, args.decimal)
    except (ValueError, OSError) as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 2
    finally:
        db.close()
    print(f"{path}  ({n} linhas)")
    return 0


def import_cli(args) -> int:
    """Importações pela linha de comandos, sem abrir a janela."""
    from perennia.core import file_import
    from perennia.core.db import Database
    from perennia.datadir import data_dir_for, database_path
    kind, path = args.importar
    if kind not in file_import.KINDS:
        print("Tipo desconhecido: " + kind + "\nExistem: hrv4training, analises, "
              "trainingpeaks, atividade, csv, saude", file=sys.stderr)
        return 2
    if not Path(path).is_file():
        print(f"Erro: não encontro {path}", file=sys.stderr)
        return 2
    db = Database(database_path(data_dir_for(args.data_dir)))
    try:
        _rep, text = file_import.import_file(db, kind, path)
    except Exception as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()
    print(text)
    return 0


def backup_cli(args) -> int:
    """Backups pela linha de comandos, sem abrir a janela."""
    from perennia.core import backup
    from perennia.core.db import Database
    from perennia.datadir import data_dir_for, database_path
    data_dir = data_dir_for(args.data_dir)
    keys = [k.strip() for k in args.componentes.split(",")] if args.componentes else None
    unknown = [k for k in keys or [] if k not in backup.BY_KEY]
    if unknown:
        print("Componentes desconhecidas: " + ", ".join(unknown) + "\nExistem: "
              + ", ".join(backup.BY_KEY), file=sys.stderr)
        return 2
    db = Database(database_path(data_dir))
    try:
        if args.restore:
            return backup.cli_restore(db, data_dir, args.restore, keys,
                                      "merge" if args.modo == "juntar" else "replace")
        return backup.cli_export(db, data_dir, args.backup or None, keys, args.credenciais)
    except backup.BackupError as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


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
