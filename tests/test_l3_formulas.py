"""v2 L3 전개 식 (cutplan_agent/skills/l3_rules.py) 을 회사 담당자 계산 문서의 예제와 받은 커팅플랜으로 확인한다.
문서: skills/01_core_knowledge/shell_cone_head_unfold.md. 예제의 지름은 평균지름이라 t=0 으로 넣는다."""

import math
import unittest

from cutplan_agent.config import density_of
from cutplan_agent.skills.l3_rules import (
    _cone,
    _cyl,
    _ecc_cone,
    _ecc_piece,
    _head_blank,
    _sector_bbox,
)


class DocumentExamplesTest(unittest.TestCase):
    def test_shell_2_4(self):
        # ID 1,500, t 12 -> Dm 1,512, L = pi x 1,512 ≈ 4,750
        self.assertAlmostEqual(_cyl(1500, 12, 3000)["blank_w"], 4750.1, delta=0.1)

    def test_concentric_cone_3_1(self):
        # D1 2,000, D2 1,000, H 800 -> R1 ≈ 1,887, R2 ≈ 943, theta ≈ 190.8°
        c = _cone(2000, 1000, 800, 0)
        self.assertAlmostEqual(c["R1"], 1886.8, delta=0.5)
        self.assertAlmostEqual(c["R2"], 943.4, delta=0.5)
        self.assertAlmostEqual(c["theta_deg"], 190.8, delta=0.1)
        # 1 장 약 3,774 x 2,065, 2 분할 조각 약 2,791 x 1,252. 코드는 중심각을 가로축 대칭으로 놓아
        # blank_w 가 반지름 방향이다 (문서와 가로·세로가 바뀐다)
        dims = sorted((c["blank_w"], c["blank_h"]))
        self.assertAlmostEqual(dims[1], 3774, delta=2)
        self.assertAlmostEqual(dims[0], 2065, delta=2)
        half = _sector_bbox(c["R1"], c["R2"], 0, math.radians(c["theta_deg"]) / 2)
        dims = sorted((half["blank_w"], half["blank_h"]))
        self.assertAlmostEqual(dims[1], 2791, delta=2)
        self.assertAlmostEqual(dims[0], 1252, delta=2)

    def test_eccentric_cone_3_2_table(self):
        # D1 2,000, D2 1,000, H 800, 수직면 편심 (e = 500), 12 등분
        c = _ecc_cone(2000, 1000, 800, 0, 0, n=12)
        self.assertAlmostEqual(c["apex_height"], 1600, places=6)
        self.assertAlmostEqual(c["apex_offset"], 1000, places=6)
        g = c["generators"]
        table = [  # (L1, L2, psi) 문서 표
            (1600.0, 800.0, 0.0),
            (1681.7, 840.8, 17.93),
            (1886.8, 943.4, 33.26),
            (2135.4, 1067.7, 46.25),
            (2358.0, 1179.0, 58.20),
            (2508.4, 1254.2, 69.89),
            (2561.2, 1280.6, 81.55),
            (2508.4, 1254.2, 93.21),
            (2358.0, 1179.0, 104.90),
            (2135.4, 1067.7, 116.86),
            (1886.8, 943.4, 129.84),
            (1681.7, 840.8, 145.18),
            (1600.0, 800.0, 163.10),
        ]
        for row, (L1, L2, psi) in zip(g, table):
            self.assertAlmostEqual(row["L1"], L1, delta=0.15)
            self.assertAlmostEqual(row["L2"], L2, delta=0.15)
            self.assertAlmostEqual(row["psi_deg"], psi, delta=0.02)
        self.assertAlmostEqual(g[0]["slant"], 800.0, delta=0.1)  # 수직면 = H
        two = [_ecc_piece(c["_gens"], 0, 6), _ecc_piece(c["_gens"], 6, 12)]
        self.assertAlmostEqual(sum(p["area"] for p in two), c["area"], delta=1.0)

    def test_head_4_6(self):
        # OD 1,000, t 10, SF 50, 트림 30 -> Dm 990, 1.2 x 990 + 100 + 30 = 1,318 -> 약 1,320
        h = _head_blank(1000 - 2 * 10, 10, 50, "2:1 ellipsoidal", trim=30)
        self.assertEqual(h["blank_dia"], 1320.0)

    def test_head_kinds(self):
        hemi = _head_blank(1000, 10, 0, "hemispherical", trim=0)
        self.assertEqual(hemi["blank_dia"], round(1.414 * 1010 / 10) * 10)
        fd = _head_blank(1000, 10, 50, "torispherical F&D", trim=0)
        od = 1020
        self.assertEqual(
            fd["blank_dia"], round((od + od / 24 + 100 + 2 / 3 * 0.1 * od) / 10) * 10
        )
        self.assertTrue(fd["warnings"])  # IKR 없음

    def test_density(self):
        self.assertEqual(density_of("SA240-304L"), 7.93e-6)
        self.assertEqual(density_of("A240-S31803"), 7.93e-6)
        self.assertEqual(density_of("SA516-70"), 7.85e-6)


class ReceivedCuttingPlanTest(unittest.TestCase):
    """test_data/cases 의 실제 값 (docs/data/cutplan_cases.md 6절). 받은 도면에서 읽은 ID, t, SF."""

    def test_heads_within_20mm(self):
        for ID, t, sf, actual in (
            (3700, 23, 38, 4590),
            (1500, 10, 27, 1890),
            (1500, 8, 27, 1878),
        ):
            got = _head_blank(ID, t, sf, "2:1 ELLIP")["blank_dia"]
            self.assertLessEqual(abs(got - actual), 20, (ID, t, sf, got, actual))

    def test_shells(self):
        self.assertAlmostEqual(
            _cyl(3700, 25, 2662)["blank_w"], 11702.5, delta=0.5
        )  # D-1203
        self.assertAlmostEqual(
            _cyl(1500, 8, 1823)["blank_w"], 4737.5, delta=0.5
        )  # S-2120 (CP 4738)


if __name__ == "__main__":
    unittest.main()
