"""Testes dos protocolos BLE e ANT+ contra pacotes construídos à mão.

Não precisam de hardware nem das bibliotecas de rádio: validam
exclusivamente a codificação e descodificação de bytes, que é onde os erros
de protocolo se escondem.
"""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from velo.io import ant, ble


class TestBleUuids(unittest.TestCase):
    def test_expansion_to_the_bluetooth_base(self):
        self.assertEqual(ble.uuid16(0x1826), "00001826-0000-1000-8000-00805f9b34fb")
        self.assertEqual(ble.uuid16(0x2AD2), "00002ad2-0000-1000-8000-00805f9b34fb")
        self.assertEqual(ble.SVC_HRS, "0000180d-0000-1000-8000-00805f9b34fb")

    def test_classify_roles(self):
        self.assertEqual(ble.classify([ble.SVC_FTMS])[1], "trainer")
        self.assertEqual(ble.classify([ble.SVC_CPS])[1], "power_meter")
        self.assertEqual(ble.classify([ble.SVC_HRS])[1], "hr_monitor")
        self.assertEqual(ble.classify([ble.SVC_CSCS])[1], "speed_cadence")
        profiles, role = ble.classify([ble.SVC_FTMS.upper(), ble.SVC_CPS])
        self.assertEqual(sorted(profiles), ["cps", "ftms"])
        self.assertEqual(role, "trainer")          # o trainer manda
        self.assertEqual(ble.classify([])[0], [])


class TestIndoorBikeData(unittest.TestCase):
    def test_speed_cadence_power(self):
        # flags 0x0044: cadência (bit 2) e potência (bit 6); bit 0 a zero
        # significa que a velocidade instantânea está presente
        r = ble.parse_indoor_bike(bytes.fromhex("4400c409b400c800"))
        self.assertAlmostEqual(r.speed_mps, 25.0 / 3.6, places=4)
        self.assertEqual(r.cadence_rpm, 90)
        self.assertEqual(r.power_w, 200)
        self.assertIsNone(r.hr_bpm)

    def test_with_distance_and_heart_rate(self):
        r = ble.parse_indoor_bike(bytes.fromhex("5402c409b400e8030 0c80055".replace(" ", "")))
        self.assertEqual(r.cadence_rpm, 90)
        self.assertEqual(r.power_w, 200)
        self.assertEqual(r.hr_bpm, 85)

    def test_more_data_bit_is_inverted(self):
        """Bit 0 a 1 ("More Data") significa que a velocidade NÃO vem."""
        r = ble.parse_indoor_bike(bytes.fromhex("4100f6ff"))
        self.assertIsNone(r.speed_mps)
        self.assertEqual(r.power_w, -10)           # potência negativa é legítima

    def test_energy_block_is_skipped_correctly(self):
        # bits 6 (potência), 8 (energia), 9 (FC) → 0x0340 ; bit0 a 1
        flags = (1 << 0) | (1 << 6) | (1 << 8) | (1 << 9)
        data = struct.pack("<HhHHBB", flags, 240, 100, 50, 5, 148)
        r = ble.parse_indoor_bike(data)
        self.assertEqual(r.power_w, 240)
        self.assertEqual(r.hr_bpm, 148)

    def test_truncated_packets_do_not_crash(self):
        self.assertIsNone(ble.parse_indoor_bike(b"").power_w)
        self.assertIsNone(ble.parse_indoor_bike(bytes.fromhex("4400c4")).power_w)
        self.assertIsNone(ble.parse_indoor_bike(bytes.fromhex("44")).power_w)


class TestCyclingPower(unittest.TestCase):
    def test_power_balance_and_torque(self):
        r, raw = ble.parse_cps(bytes.fromhex("0500fa0068800c"))
        self.assertEqual(r.power_w, 250)
        self.assertAlmostEqual(r.balance_left, 52.0)
        self.assertAlmostEqual(raw["torque_acc"], 100.0)

    def test_power_only(self):
        r, raw = ble.parse_cps(bytes.fromhex("00009600"))
        self.assertEqual(r.power_w, 150)
        self.assertIsNone(r.balance_left)
        self.assertEqual(raw, {})

    def test_crank_revolutions_give_cadence(self):
        flags = (1 << 5)
        a = ble.parse_cps(struct.pack("<HhHH", flags, 200, 100, 1024))[1]
        b = ble.parse_cps(struct.pack("<HhHH", flags, 200, 102, 2048))[1]
        self.assertAlmostEqual(ble.cadence_from_cranks(a, b), 120.0)

    def test_crank_counter_rollover(self):
        flags = (1 << 5)
        a = ble.parse_cps(struct.pack("<HhHH", flags, 200, 65535, 65000))[1]
        b = ble.parse_cps(struct.pack("<HhHH", flags, 200, 1, 488))[1]
        self.assertAlmostEqual(ble.cadence_from_cranks(a, b), 120.0)

    def test_implausible_cadence_is_rejected(self):
        a = {"crank_revs": 0, "crank_time": 0}
        b = {"crank_revs": 100, "crank_time": 1024}     # 6000 rpm
        self.assertIsNone(ble.cadence_from_cranks(a, b))

    def test_no_time_advance_returns_none(self):
        a = {"crank_revs": 10, "crank_time": 1024}
        self.assertIsNone(ble.cadence_from_cranks(a, dict(a)))


class TestHeartRateAndCsc(unittest.TestCase):
    def test_8_and_16_bit(self):
        self.assertEqual(ble.parse_hr(bytes.fromhex("0048")), 72)
        self.assertEqual(ble.parse_hr(bytes.fromhex("014800")), 72)
        self.assertIsNone(ble.parse_hr(b""))

    def test_csc_wheel_speed(self):
        data = struct.pack("<BIH", 0x01, 1000, 1024)
        a = ble.parse_csc(data)
        b = ble.parse_csc(struct.pack("<BIH", 0x01, 1005, 2048))
        mps = ble.speed_from_wheel(a, b, circumference_m=2.0)
        self.assertAlmostEqual(mps, 10.0)

    def test_csc_both_fields(self):
        data = struct.pack("<BIHHH", 0x03, 500, 1024, 200, 1024)
        out = ble.parse_csc(data)
        self.assertEqual(out["wheel_revs"], 500)
        self.assertEqual(out["crank_revs"], 200)


class TestFtmsControl(unittest.TestCase):
    def test_encode_simulation(self):
        # declive 3,00 % → 300 = 0x012C ; crr 0,004 → 40 ; cw 0,32 → 32
        self.assertEqual(ble.encode_sim(3.0, 0.004, 0.32, 0.0),
                         bytes.fromhex("11000 02c012820".replace(" ", "")))

    def test_encode_negative_gradient(self):
        self.assertEqual(ble.encode_sim(-3.0), bytes.fromhex("1100 00d4fe2820".replace(" ", "")))

    def test_encode_target_power(self):
        self.assertEqual(ble.encode_target_power(250), bytes.fromhex("05fa00"))
        self.assertEqual(ble.encode_target_power(0), bytes.fromhex("050000"))

    def test_encode_resistance_and_spindown(self):
        # nível 12,0 → 120 ; a escala do FTMS é 0–25,5, não percentagem
        self.assertEqual(ble.encode_target_resistance_level(12.0), bytes.fromhex("0478"))
        self.assertEqual(ble.encode_target_resistance_level(99.0), bytes.fromhex("04fe"))  # 0xFF é reservado
        self.assertAlmostEqual(ble.resistance_level_from_pct(100.0), 25.5)
        self.assertAlmostEqual(ble.resistance_level_from_pct(0.0), 0.0)
        self.assertEqual(ble.encode_spindown(True), bytes.fromhex("1301"))
        self.assertEqual(ble.encode_spindown(False), bytes.fromhex("1302"))

    def test_extreme_values_are_clamped(self):
        payload = ble.encode_sim(10_000.0, 10.0, 10.0)
        self.assertEqual(len(payload), 7)
        self.assertEqual(payload[5], 255)
        self.assertEqual(payload[6], 255)

    def test_feature_decoding(self):
        data = struct.pack("<II", (1 << 1) | (1 << 14), (1 << 3) | (1 << 13) | (1 << 15))
        f = ble.parse_ftms_feature(data)
        self.assertTrue(f["cadence"] and f["power"])
        self.assertTrue(f["erg"] and f["sim"] and f["spindown"])
        self.assertFalse(f["resistance"])

    def test_trainer_without_simulation(self):
        f = ble.parse_ftms_feature(struct.pack("<II", 0, (1 << 2)))
        self.assertTrue(f["resistance"])
        self.assertFalse(f["sim"])
        self.assertFalse(f["erg"])

    def test_short_feature_block_is_safe(self):
        f = ble.parse_ftms_feature(b"\x00\x00")
        self.assertFalse(f["sim"])

    def test_control_response(self):
        self.assertEqual(ble.parse_control_response(bytes.fromhex("801101")), (0x11, 0x01))
        self.assertIsNone(ble.parse_control_response(bytes.fromhex("1101")))
        self.assertIsNone(ble.parse_control_response(b"\x80"))


class TestAntFraming(unittest.TestCase):
    def test_checksum_and_build(self):
        msg = ant.build_message(ant.MSG_OPEN_CHANNEL, bytes((0,)))
        self.assertEqual(msg[0], ant.SYNC)
        self.assertEqual(msg[1], 1)
        self.assertEqual(msg[2], ant.MSG_OPEN_CHANNEL)
        self.assertEqual(ant.checksum(msg[:-1]), msg[-1])

    def test_parse_two_messages(self):
        a = ant.build_message(ant.MSG_BROADCAST_DATA, bytes(range(9)))
        b = ant.build_message(ant.MSG_CHANNEL_EVENT, bytes((0, 1, 7)))
        msgs, rest = ant.parse_messages(a + b)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0][0], ant.MSG_BROADCAST_DATA)
        self.assertEqual(msgs[1][1], bytes((0, 1, 7)))
        self.assertEqual(rest, b"")

    def test_partial_message_is_kept_for_later(self):
        a = ant.build_message(ant.MSG_BROADCAST_DATA, bytes(range(9)))
        msgs, rest = ant.parse_messages(a[:-3])
        self.assertEqual(msgs, [])
        self.assertEqual(rest, a[:-3])
        # chega o resto
        msgs, rest = ant.parse_messages(rest + a[-3:])
        self.assertEqual(len(msgs), 1)
        self.assertEqual(rest, b"")

    def test_resynchronizes_after_noise(self):
        good = ant.build_message(ant.MSG_CHANNEL_EVENT, bytes((0, 1, 7)))
        msgs, _ = ant.parse_messages(b"\x12\x34\x56" + good)
        self.assertEqual(len(msgs), 1)

    def test_bad_checksum_is_discarded(self):
        good = bytearray(ant.build_message(ant.MSG_CHANNEL_EVENT, bytes((0, 1, 7))))
        good[-1] ^= 0xFF
        msgs, _ = ant.parse_messages(bytes(good))
        self.assertEqual(msgs, [])


class TestFecControlPages(unittest.TestCase):
    def test_track_resistance_encodes_gradient(self):
        page = ant.encode_track_resistance(3.0, 0.004)
        self.assertEqual(len(page), 8)
        self.assertEqual(page[0], ant.PAGE_TRACK_RESISTANCE)
        grade = struct.unpack("<H", page[5:7])[0]
        self.assertEqual(grade, 20300)                   # (3 + 200) × 100
        self.assertEqual(page[7], 80)                    # 0,004 / 5e-5

    def test_negative_gradient_uses_the_offset(self):
        grade = struct.unpack("<H", ant.encode_track_resistance(-5.0)[5:7])[0]
        self.assertEqual(grade, 19500)                   # (−5 + 200) × 100

    def test_target_power_quarter_watts(self):
        page = ant.encode_target_power(250)
        self.assertEqual(page[0], ant.PAGE_TARGET_POWER)
        self.assertEqual(struct.unpack("<H", page[6:8])[0], 1000)

    def test_basic_resistance_half_percent(self):
        page = ant.encode_basic_resistance(50.0)
        self.assertEqual(page[0], ant.PAGE_BASIC_RESISTANCE)
        self.assertEqual(page[7], 100)

    def test_user_config_length(self):
        page = ant.encode_user_config(72.0, 8.0)
        self.assertEqual(len(page), 8)
        self.assertEqual(page[0], ant.PAGE_USER_CONFIG)
        self.assertEqual(struct.unpack("<H", page[1:3])[0], 7200)   # 72 kg em 0,01 kg

    def test_calibration_request_sets_spindown_bit(self):
        page = ant.encode_calibration_request(spindown=True)
        self.assertEqual(page[0], ant.PAGE_CALIBRATION_REQUEST)
        self.assertTrue(page[1] & 0x80)
        self.assertFalse(page[1] & 0x40)


class TestFecDataPages(unittest.TestCase):
    def test_trainer_data_12_bit_power(self):
        data = bytes((ant.PAGE_TRAINER_DATA, 10, 85, 0xE8, 0x03, 0xFA, 0x00, 0x00))
        d = ant.decode_trainer_data(data)
        self.assertEqual(d["power_w"], 250)
        self.assertEqual(d["cadence_rpm"], 85)
        self.assertEqual(d["accumulated_power"], 1000)
        self.assertFalse(d["calibration_needed"])

    def test_power_above_255_spans_two_bytes(self):
        data = bytes((ant.PAGE_TRAINER_DATA, 11, 90, 0xE8, 0x03, 0x58, 0x02, 0x00))
        self.assertEqual(ant.decode_trainer_data(data)["power_w"], 600)

    def test_status_nibble_does_not_corrupt_power(self):
        # estado 1 (calibração necessária) no nibble alto do byte 6
        data = bytes((ant.PAGE_TRAINER_DATA, 11, 90, 0xE8, 0x03, 0x58, 0x12, 0x00))
        d = ant.decode_trainer_data(data)
        self.assertEqual(d["power_w"], 600)
        self.assertTrue(d["calibration_needed"])

    def test_invalid_fields_are_omitted(self):
        data = bytes((ant.PAGE_TRAINER_DATA, 10, 0xFF, 0xFF, 0xFF, 0xFF, 0x0F, 0x00))
        d = ant.decode_trainer_data(data)
        self.assertNotIn("cadence_rpm", d)
        self.assertNotIn("power_w", d)

    def test_general_fe_speed_and_hr(self):
        data = bytes((ant.PAGE_GENERAL_FE, 25, 40, 200, 0x40, 0x1F, 150, 0x30))
        d = ant.decode_general_fe(data)
        self.assertAlmostEqual(d["speed_mps"], 8.0)
        self.assertEqual(d["hr_bpm"], 150)
        self.assertAlmostEqual(d["elapsed_s"], 10.0)
        self.assertEqual(d["distance_m"], 200)

    def test_general_fe_without_hr(self):
        data = bytes((ant.PAGE_GENERAL_FE, 25, 40, 200, 0x40, 0x1F, 0xFF, 0x30))
        self.assertNotIn("hr_bpm", ant.decode_general_fe(data))

    def test_power_only_balance_left(self):
        data = bytes((0x10, 5, 52, 85, 0xD0, 0x07, 0x2C, 0x01))
        d = ant.decode_power_only(data)
        self.assertEqual(d["power_w"], 300)
        self.assertEqual(d["cadence_rpm"], 85)
        self.assertAlmostEqual(d["balance_left"], 52.0)

    def test_power_only_balance_reported_as_right(self):
        # bit 7 ligado: o valor refere-se à perna direita (48 %)
        data = bytes((0x10, 5, 0x80 | 48, 85, 0xD0, 0x07, 0x2C, 0x01))
        self.assertAlmostEqual(ant.decode_power_only(data)["balance_left"], 52.0)

    def test_crank_torque_average(self):
        prev = ant.decode_crank_torque(bytes((0x12, 10, 5, 85, 0x00, 0x04, 0xE8, 0x03)))
        now = ant.decode_crank_torque(bytes((0x12, 12, 7, 85, 0x00, 0x08, 0x68, 0x04)))
        self.assertAlmostEqual(ant.torque_from_crank(prev, now), 2.0)

    def test_torque_rollover(self):
        prev = {"event_count": 254, "accumulated_torque": 65500}
        now = {"event_count": 2, "accumulated_torque": 92}
        # d_event = 4, d_torque = 128 → 128 / (32 × 4) = 1,0 Nm
        self.assertAlmostEqual(ant.torque_from_crank(prev, now), 1.0)

    def test_heart_rate_page(self):
        self.assertEqual(ant.decode_hr(bytes((0x00, 1, 2, 3, 4, 5, 6, 145)))["hr_bpm"], 145)
        self.assertEqual(ant.decode_hr(bytes((0x00, 1, 2, 3, 4, 5, 6, 0))), {})

    def test_calibration_progress_and_result(self):
        prog = ant.decode_calibration_progress(
            bytes((ant.PAGE_CALIBRATION_PROGRESS, 0x80, 0xFF, 100, 0xFF, 0xFF, 0x40, 0x1F)))
        self.assertTrue(prog["spindown_pending"])
        self.assertAlmostEqual(prog["temperature_c"], 25.0)
        self.assertAlmostEqual(prog["target_speed_mps"], 8.0)

        res = ant.decode_calibration_response(
            bytes((ant.PAGE_CALIBRATION_REQUEST, 0x80, 0xFF, 0xFF, 0xFF, 0xFF, 0xE8, 0x03)))
        self.assertTrue(res["success"])
        self.assertEqual(res["spindown_time_ms"], 1000)

    def test_short_pages_are_safe(self):
        for fn in (ant.decode_trainer_data, ant.decode_general_fe,
                   ant.decode_power_only, ant.decode_crank_torque, ant.decode_hr,
                   ant.decode_calibration_progress, ant.decode_calibration_response):
            self.assertEqual(fn(b"\x19\x00"), {})


class TestAntDiscovered(unittest.TestCase):
    def test_roles_and_ids(self):
        fec = ant.AntDiscovered(1234, ant.DEVICE_FEC, "trainer")
        self.assertEqual(fec.role, "trainer")
        self.assertTrue(fec.can_control)
        self.assertEqual(fec.device_id, "ant:1234:17")

        hr = ant.AntDiscovered(99, ant.DEVICE_HR, "cinta")
        self.assertEqual(hr.role, "hr_monitor")
        self.assertFalse(hr.can_control)


class TestGracefulWithoutLibraries(unittest.TestCase):
    """Sem bleak nem pyusb instalados, a aplicação tem de continuar a arrancar."""

    def test_scan_returns_empty_instead_of_raising(self):
        if not ble.bleak_available():
            self.assertEqual(ble.scan(timeout=0.1), [])
        if not ant.pyusb_available():
            self.assertIsNone(ant.find_stick())
            stick, found = ant.scan(timeout=0.1)
            self.assertIsNone(stick)
            self.assertEqual(found, [])


class _FakeEndpoint:
    def __init__(self):
        self.written: list[bytes] = []

    def write(self, data, timeout=0):
        self.written.append(bytes(data))


def _msgs(ep) -> list[tuple[int, bytes]]:
    out = []
    for frame in ep.written:
        out.extend(ant.parse_messages(frame)[0])
    return out


class TestAntDiscovery(unittest.TestCase):
    """A procura ANT+ com uma antena falsa: o que vai e o que vem pelo USB."""

    def setUp(self):
        self.stick = ant.AntStick()
        self.ep = _FakeEndpoint()
        self.stick._ep_out = self.ep

    def broadcast(self, channel: int, page: bytes) -> None:
        self.stick._dispatch(ant.MSG_BROADCAST_DATA, bytes((channel,)) + page)

    def test_first_data_asks_who_the_device_is(self):
        self.broadcast(1, bytes((0x10, 1, 0x80 | 52, 85, 0, 0, 0xF0, 0)))
        self.assertIn((ant.MSG_REQUEST, bytes((1, ant.MSG_CHANNEL_ID))), _msgs(self.ep))
        # só pergunta uma vez
        self.broadcast(1, bytes((0x10, 2, 0x80 | 52, 85, 0, 0, 0xF0, 0)))
        asks = [m for m in _msgs(self.ep) if m[0] == ant.MSG_REQUEST]
        self.assertEqual(len(asks), 1)

    def test_channel_id_reply_strips_the_pairing_bit(self):
        # Assioma #4321, tipo 11 com o bit de emparelhamento (0x8B)
        self.stick._dispatch(ant.MSG_CHANNEL_ID, struct.pack("<BHBB", 1, 4321, 0x8B, 5))
        info = self.stick.found[1]
        self.assertEqual(info.device_number, 4321)
        self.assertEqual(info.device_type, ant.DEVICE_POWER)
        self.assertEqual(info.role, "power_meter")
        self.assertEqual(info.name, "ANT+ Potência #4321")

    def test_number_zero_means_still_searching(self):
        self.broadcast(2, bytes(8))
        self.stick._dispatch(ant.MSG_CHANNEL_ID, struct.pack("<BHBB", 2, 0, 120, 0))
        self.assertNotIn(2, self.stick.found)
        self.broadcast(2, bytes(8))                       # volta a perguntar
        asks = [m for m in _msgs(self.ep) if m[0] == ant.MSG_REQUEST]
        self.assertEqual(len(asks), 2)

    def test_exclusion_list_is_sent_before_opening(self):
        ant.time.sleep, real = (lambda s: None), ant.time.sleep
        try:
            self.stick.open_channel(3, ant.DEVICE_POWER, exclude=(555,))
        finally:
            ant.time.sleep = real
        ids = [m[0] for m in _msgs(self.ep)]
        self.assertLess(ids.index(ant.MSG_ADD_TO_LIST), ids.index(ant.MSG_OPEN_CHANNEL))
        self.assertLess(ids.index(ant.MSG_CONFIG_LIST), ids.index(ant.MSG_OPEN_CHANNEL))
        add = [p for i, p in _msgs(self.ep) if i == ant.MSG_ADD_TO_LIST][0]
        self.assertEqual(struct.unpack("<BHBBB", add), (3, 555, ant.DEVICE_POWER, 0, 0))
        cfg = [p for i, p in _msgs(self.ep) if i == ant.MSG_CONFIG_LIST][0]
        self.assertEqual(cfg, bytes((3, 1, 1)))           # 1 entrada, excluir


class _ScriptedStick:
    """Antena que vai «encontrando» dispositivos à medida que o tempo passa."""

    def __init__(self, script):
        self.script = script          # [(segundo, canal, número, tipo)]
        self.now = 0.0
        self.opened: list[tuple] = []
        self._found: dict = {}

    def open_channel(self, channel, device_type, device_number=0, exclude=(), note=""):
        self.opened.append((channel, device_type, tuple(exclude)))

    @property
    def found(self):
        for at, ch, number, dtype in self.script:
            if self.now >= at and ch not in self._found and \
                    any(o[0] == ch for o in self.opened):
                self._found[ch] = ant.AntDiscovered(number, dtype,
                                                    ant.device_name(dtype, number))
        return dict(self._found)

    def sleep(self, s):
        self.now += s

    def clock(self):
        return self.now


class TestAntScanTrainerAndPedals(unittest.TestCase):
    def test_power_channel_that_grabs_the_trainer_is_redone_without_it(self):
        stick = _ScriptedStick([
            (1.0, 0, 555, ant.DEVICE_FEC),       # rolo
            (1.5, 1, 555, ant.DEVICE_POWER),     # o mesmo rolo, como medidor
            (2.0, 2, 77, ant.DEVICE_HR),
            (4.0, 3, 4321, ant.DEVICE_POWER),    # a Assioma, no canal novo
        ])
        ant.run_scan(stick, timeout=10, sleep=stick.sleep, clock=stick.clock)
        self.assertIn((3, ant.DEVICE_POWER, (555,)), stick.opened)
        found = stick.found
        self.assertTrue(found[1].trainer_twin)
        self.assertEqual(found[3].device_number, 4321)
        self.assertFalse(found[3].trainer_twin)
        self.assertLess(stick.now, 10)                   # acabou quando encontrou tudo

    def test_pedals_alone_need_no_extra_channel(self):
        stick = _ScriptedStick([(1.0, 1, 4321, ant.DEVICE_POWER)])
        ant.run_scan(stick, timeout=3, sleep=stick.sleep, clock=stick.clock)
        self.assertEqual([o[0] for o in stick.opened], [0, 1, 2])
        self.assertEqual(stick.found[1].device_number, 4321)


class TestPedalsBeatTheTrainer(unittest.TestCase):
    """Rolo e Assioma em simultâneo: potência e balanço vêm sempre dos pedais."""

    def test_priority_is_applied_to_push_sensors(self):
        from velo.io.hub import SensorHub
        hub = SensorHub()
        stick = ant.AntStick()
        trainer = ant.AntSensor(stick, 0, ant.AntDiscovered(555, ant.DEVICE_FEC, "rolo"), hub)
        pedals = ant.AntSensor(stick, 3,
                               ant.AntDiscovered(4321, ant.DEVICE_POWER, "assioma"), hub)
        hub.add_source(trainer, role="trainer", is_trainer=True)
        hub.add_source(pedals, role="power_meter")
        fec_page = bytes((ant.PAGE_TRAINER_DATA, 10, 88, 0, 0, 0xFA, 0x00, 0x00))  # 250 W
        pedal_page = bytes((0x10, 5, 0x80 | 52, 86, 0, 0, 0xF0, 0x00))               # 240 W
        for _ in range(5):
            # a ordem alterna; o resultado não pode alternar
            trainer._on_page(0, fec_page)
            pedals._on_page(3, pedal_page)
            self.assertEqual(hub.reading().power_w, 240)
            pedals._on_page(3, pedal_page)
            trainer._on_page(0, fec_page)
            r = hub.reading()
            self.assertEqual(r.power_w, 240)
            self.assertAlmostEqual(r.balance_left, 48.0)
            self.assertEqual(r.cadence_rpm, 86)
        self.assertIs(hub.trainer, trainer)              # a resistência é do rolo


class TestTorqueEffectivenessAndSmoothness(unittest.TestCase):
    def test_left_and_right(self):
        # 0x13, evento 7, TE 78 % / 80,5 %, PS 22 % / 24,5 %
        d = ant.decode_te_ps(bytes((0x13, 7, 156, 161, 44, 49, 0xFF, 0xFF)))
        self.assertEqual(d["te_left"], 78.0)
        self.assertEqual(d["te_right"], 80.5)
        self.assertEqual(d["ps_left"], 22.0)
        self.assertEqual(d["ps_right"], 24.5)
        self.assertNotIn("ps_combined", d)

    def test_combined_smoothness_and_invalid_bytes(self):
        d = ant.decode_te_ps(bytes((0x13, 7, 0xFF, 0xFF, 50, 0xFE, 0xFF, 0xFF)))
        self.assertEqual(d, {"event_count": 7, "ps_combined": 25.0})

    def test_pedals_push_them_to_the_hub(self):
        from velo.io.hub import SensorHub
        hub = SensorHub()
        pedals = ant.AntSensor(ant.AntStick(), 3,
                               ant.AntDiscovered(4321, ant.DEVICE_POWER, "assioma"), hub)
        hub.add_source(pedals, role="power_meter")
        pedals._on_page(3, bytes((0x13, 7, 156, 161, 44, 49, 0xFF, 0xFF)))
        r = hub.reading()
        self.assertEqual((r.te_left, r.te_right, r.ps_left, r.ps_right),
                         (78.0, 80.5, 22.0, 24.5))
        self.assertIsNone(r.ps_combined)


class _FakeBleDevice:
    def __init__(self, address, name, role, can_control=False):
        self.address, self.name, self.role = address, name, role
        self.can_control = can_control

    @property
    def device_id(self):
        return f"ble:{self.address}"


class _FakeSensor:
    def __init__(self, transport, device_id, ok=True):
        self.transport, self.device_id, self.ok = transport, device_id, ok
        self.name = device_id
        self._priority = {}

    def connect(self):
        return self.ok

    def reading(self):
        return None


class TestAutoConnect(unittest.TestCase):
    """ANT+ primeiro; o que falhar vai por Bluetooth; o rolo só por um caminho."""

    def setUp(self):
        from velo.io import autoconnect
        self.ac = autoconnect
        self.ant_pedals = ant.AntDiscovered(4321, ant.DEVICE_POWER, "ANT+ Potência #4321")
        self.ant_fec = ant.AntDiscovered(555, ant.DEVICE_FEC, "ANT+ Rolo FE-C #555")
        self.ble_pedals = _FakeBleDevice("AA:01", "ASSIOMA", "power_meter")
        self.ble_trainer = _FakeBleDevice("BB:02", "KICKR", "trainer", can_control=True)
        self.ble_strap = _FakeBleDevice("CC:03", "HRM", "hr_monitor")
        self.known = [
            {"id": self.ant_pedals.device_id, "transport": "ant"},
            {"id": self.ant_fec.device_id, "transport": "ant"},
            {"id": self.ble_pedals.device_id, "transport": "ble"},
            {"id": self.ble_trainer.device_id, "transport": "ble"},
            {"id": self.ble_strap.device_id, "transport": "ble"},
        ]
        self.ble_calls = 0

    def run_with(self, pref, ant_found=None, stick=True, ble_found=None):
        def ant_scan():
            return ("stick" if stick else None), (ant_found or [])

        def ble_scan():
            self.ble_calls += 1
            return ble_found or []

        return self.ac.connect_known(
            self.known, pref, ant_scan=ant_scan,
            make_ant=lambda st, ch, info: _FakeSensor("ant", info.device_id),
            ble_scan=ble_scan, make_ble=lambda d: _FakeSensor("ble", d.device_id))

    def ids(self, res):
        return [src.device_id for src, _, _ in res.sources]

    def test_ant_first_keeps_bluetooth_as_backup_but_not_for_the_trainer(self):
        res = self.run_with(self.ac.ANT_FIRST,
                            ant_found=[(0, self.ant_fec), (1, self.ant_pedals)],
                            ble_found=[self.ble_pedals, self.ble_trainer, self.ble_strap])
        self.assertEqual(self.ids(res), [self.ant_fec.device_id, self.ant_pedals.device_id,
                                         self.ble_pedals.device_id, self.ble_strap.device_id])
        self.assertNotIn(self.ble_trainer.device_id, self.ids(res))   # já há rolo por ANT+
        self.assertIn("Bluetooth ASSIOMA (reserva)", res.lines)

    def test_no_stick_falls_back_to_bluetooth(self):
        res = self.run_with(self.ac.ANT_FIRST, stick=False,
                            ble_found=[self.ble_pedals, self.ble_trainer])
        self.assertEqual(self.ids(res), [self.ble_pedals.device_id,
                                         self.ble_trainer.device_id])
        self.assertIn("ANT+: antena indisponível", res.lines)

    def test_strangers_are_ignored(self):
        neighbour = ant.AntDiscovered(9999, ant.DEVICE_POWER, "pedais do vizinho")
        res = self.run_with(self.ac.ANT_ONLY, ant_found=[(1, neighbour), (3, self.ant_pedals)])
        self.assertEqual(self.ids(res), [self.ant_pedals.device_id])
        self.assertEqual(self.ble_calls, 0)                       # só ANT+

    def test_bluetooth_first_takes_the_trainer_by_bluetooth(self):
        res = self.run_with(self.ac.BLE_FIRST, ant_found=[(0, self.ant_fec)],
                            ble_found=[self.ble_trainer])
        self.assertEqual(self.ids(res), [self.ble_trainer.device_id])

    def test_nothing_known_does_nothing(self):
        self.known = []
        res = self.run_with(self.ac.ANT_FIRST)
        self.assertEqual(res.sources, [])
        self.assertEqual(self.ble_calls, 0)


class TestTransportFailover(unittest.TestCase):
    """A mesma Assioma por ANT+ e por Bluetooth: ANT+ manda, Bluetooth cobre."""

    def test_ant_wins_and_bluetooth_takes_over_when_it_drops(self):
        from velo.io.hub import SensorHub
        now = [0.0]
        hub = SensorHub(clock=lambda: now[0])
        hub.preferred_transport = "ant"
        ant_src = _FakeSensor("ant", "ant:4321:11")
        ble_src = _FakeSensor("ble", "ble:AA:01")
        hub.add_source(ant_src, role="power_meter")
        hub.add_source(ble_src, role="power_meter")

        def both(ant_w, ble_w):
            hub.push(ant_src.device_id, "power", ant_w, ant_src._priority["power"])
            hub.push(ble_src.device_id, "power", ble_w, ble_src._priority["power"])

        both(240, 238)
        self.assertEqual(hub.reading().power_w, 240)
        # o ANT+ cala-se; o Bluetooth continua
        for _ in range(7):
            now[0] += 1.0
            hub.push(ble_src.device_id, "power", 236, ble_src._priority["power"])
        self.assertEqual(hub.reading().power_w, 236)
        # o ANT+ volta e retoma o comando
        both(250, 249)
        self.assertEqual(hub.reading().power_w, 250)

    def test_bonus_never_beats_a_stronger_role(self):
        from velo.io.hub import SensorHub
        hub = SensorHub()
        trainer = _FakeSensor("ant", "ant:555:17")
        pedals = _FakeSensor("ble", "ble:AA:01")
        hub.add_source(trainer, role="trainer", is_trainer=True)
        hub.add_source(pedals, role="power_meter")
        self.assertGreater(pedals._priority["power"], trainer._priority["power"])
        self.assertGreater(pedals._priority["cadence"], trainer._priority["cadence"])


class TestStoppedPedalsAreZeroed(unittest.TestCase):
    """Pedais parados repetem a última página; ao fim de 3 s conta como zero."""

    def setUp(self):
        from velo.io.hub import SensorHub
        self.now = [0.0]
        self.hub = SensorHub(clock=lambda: self.now[0])
        self.pedals = ant.AntSensor(ant.AntStick(), 3,
                                    ant.AntDiscovered(4321, ant.DEVICE_POWER, "assioma"),
                                    self.hub)
        self.pedals._stall.clock = lambda: self.now[0]
        self.hub.add_source(self.pedals, role="power_meter")

    def page(self, event, watts=240, cadence=86):
        return bytes((0x10, event, 0x80 | 52, cadence, 0, 0, watts & 0xFF, watts >> 8))

    def test_repeated_event_count_becomes_zero_after_3_s(self):
        for i in range(12):                       # a pedalar: o contador sobe
            self.now[0] += 0.25
            self.pedals._on_page(3, self.page(event=i))
        self.assertEqual(self.hub.reading().power_w, 240)
        for _ in range(10):                       # parou: a mesma página, 2,5 s
            self.now[0] += 0.25
            self.pedals._on_page(3, self.page(event=11))
        self.assertEqual(self.hub.reading().power_w, 240)   # ainda dentro dos 3 s
        for _ in range(4):                        # passa dos 3 s
            self.now[0] += 0.25
            self.pedals._on_page(3, self.page(event=11))
        r = self.hub.reading()
        self.assertEqual((r.power_w, r.cadence_rpm), (0, 0))
        self.now[0] += 0.25                       # volta a pedalar
        self.pedals._on_page(3, self.page(event=12, watts=180, cadence=70))
        r = self.hub.reading()
        self.assertEqual((r.power_w, r.cadence_rpm), (180, 70))

    def test_closed_channel_of_a_sensor_in_use_is_reopened(self):
        stick = ant.AntStick()
        stick._running = True
        stick._channels[3] = ant.AntDiscovered(4321, ant.DEVICE_POWER, "assioma")
        stick._handlers[3] = lambda ch, data: None
        reopened = []
        stick.reopen = lambda ch: reopened.append(ch)
        stick._dispatch(ant.MSG_CHANNEL_EVENT, bytes((3, 1, ant.EVENT_CHANNEL_CLOSED)))
        import time as _t
        for _ in range(100):
            if reopened:
                break
            _t.sleep(0.01)
        self.assertEqual(reopened, [3])
        # um canal fechado de propósito (sem sensor ligado) não reabre
        stick._dispatch(ant.MSG_CHANNEL_EVENT, bytes((5, 1, ant.EVENT_CHANNEL_CLOSED)))
        _t.sleep(0.05)
        self.assertEqual(reopened, [3])

    def test_reopen_searches_that_device_forever(self):
        stick = ant.AntStick()
        ep = _FakeEndpoint()
        stick._ep_out = ep
        stick._channels[3] = ant.AntDiscovered(4321, ant.DEVICE_POWER, "assioma")
        real = ant.time.sleep
        ant.time.sleep = lambda s: None
        try:
            stick.reopen(3)
        finally:
            ant.time.sleep = real
        msgs = _msgs(ep)
        self.assertEqual(msgs[0], (ant.MSG_UNASSIGN_CHANNEL, bytes((3,))))
        chan_id = [p for i, p in msgs if i == ant.MSG_SET_CHANNEL_ID][0]
        self.assertEqual(struct.unpack("<BHBB", chan_id)[1], 4321)   # só estes pedais
        timeout = [p for i, p in msgs if i == ant.MSG_SET_SEARCH_TIMEOUT][0]
        self.assertEqual(timeout, bytes((3, ant.SEARCH_FOREVER)))

    def test_ble_cranks_that_stop_turning_give_zero(self):
        from velo.io.hub import SensorHub
        hub = SensorHub(clock=lambda: self.now[0])
        info = ble.Discovered("AA:01", "ASSIOMA", ["cps"], "power_meter")
        sensor = ble.BleSensor(info, hub)
        sensor._stall.clock = lambda: self.now[0]
        hub.add_source(sensor, role="power_meter")
        flags = (1 << 5)
        revs, t1024 = 100, 0
        for _ in range(8):                        # a pedalar a 90 rpm
            self.now[0] += 0.66
            revs += 1
            t1024 = (t1024 + 683) % 65536
            sensor._on_cps(None, bytearray(struct.pack("<HhHH", flags, 230, revs, t1024)))
        self.assertEqual(hub.reading().power_w, 230)
        for _ in range(6):                        # parou: a mesma notificação, 4 s
            self.now[0] += 0.66
            sensor._on_cps(None, bytearray(struct.pack("<HhHH", flags, 230, revs, t1024)))
        r = hub.reading()
        self.assertEqual((r.power_w, r.cadence_rpm), (0, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
